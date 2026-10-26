import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root = Path.cwd()
out = root / 'validation-output'
out.mkdir()
compiler = os.environ['VALIDATION_COMPILER']
expected = {'original': 'a640597d6e118bf76ca2067b629fa1336f58409a',
            'fixed': 'cbb02b2468662258e288758ec4c727b2c0705e5e'}
records = {'scope': 'Standalone issue241 regression only; full B2 baseline has separate existing C-header compile failures.',
           'compiler': compiler, 'variants': {}}
test = root / 'fixed/test/issue241.cpp'
wrapper = out / 'regression.cpp'
wrapper.write_text('#include <iostream>\n#define main issue241_test_main\n#include "' +
                   test.as_posix() + '"\n#undef main\nint main() { std::cout << "wchar_bytes=" << sizeof(wchar_t) << "\\n"; return issue241_test_main(); }\n')
includes = [root / 'deps/core/include', root / 'deps/config/include']
for label in ['original', 'fixed']:
    source = root / label
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    assert head == expected[label], (label, head)
    executable = out / (label + ('.exe' if os.name == 'nt' else ''))
    paths = [source / 'include'] + includes
    if compiler == 'msvc':
        command = ['cl', '/nologo', '/EHsc', '/std:c++17', '/Zc:__cplusplus', '/permissive-',
                   '/DBOOST_REGEX_STANDALONE', '/Fe:' + str(executable),
                   '/Fo:' + str(out / (label + '.obj'))]
        command += ['/I' + str(p) for p in paths] + [str(wrapper)]
    else:
        cxx = 'g++-11' if compiler == 'gcc11' else 'clang++'
        standard = '-std=c++11' if compiler == 'gcc11' else '-std=c++17'
        command = [cxx, standard, '-O1', '-g', '-DBOOST_REGEX_STANDALONE']
        if compiler == 'clang-sanitized':
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']
        command += ['-I' + str(p) for p in paths] + [str(wrapper), '-o', str(executable)]
    with (out / (label + '-build.log')).open('w') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    assert result.returncode == 0, (label, 'build failed', result.returncode)
    result = subprocess.run([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (out / (label + '-run.log')).write_text(result.stdout)
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
              for name in ['include/boost/regex/v5/basic_regex_creator.hpp',
                           'include/boost/regex/v5/perl_matcher.hpp',
                           'include/boost/regex/v5/states.hpp']}
    records['variants'][label] = {'head': head, 'returncode': result.returncode, 'command': command,
                                 'header_sha256': hashes, 'test_sha256': hashlib.sha256(test.read_bytes()).hexdigest(),
                                 'output_tail': result.stdout[-2000:]}
    (out / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
    if label == 'original':
        assert result.returncode != 0 and re.search(r'[1-9][0-9]* errors detected\.', result.stdout), result.stdout[-2000:]
    else:
        assert result.returncode == 0 and 'No errors detected.' in result.stdout, result.stdout[-2000:]
    print(label, head, 'exit', result.returncode, flush=True)
print('Standalone original/fixed comparison passed.', flush=True)

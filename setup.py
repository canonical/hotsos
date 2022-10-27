from setuptools import setup, find_packages

setup(
    name='hotsos',
    version='1.0.0',
    packages=find_packages(include=['hotsos*']),
    install_requires=[
        'click',
        'pyyaml',
        'progress',
        'simplejson',
        'structr',
        'fasteners',
        # Pin to cryptography==3.4.8 since the cryptography-3.4.x branch is the
        # last branch that can be built without the Rust toolchain.
        # More info on issue: https://github.com/canonical/hotsos/issues/326
        # [TODO] Bump cryptography to more recent release
        'cryptography==3.4.8',
    ],
    entry_points={
      'console_scripts': [
        'hotsos=hotsos.cli:main']
    }
)

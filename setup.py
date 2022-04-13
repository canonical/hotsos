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
        'cryptography',
    ],
    entry_points={
      'console_scripts': [
        'hotsos=hotsos.cli:main']
    }
)

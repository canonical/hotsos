from setuptools import setup, find_packages

setup(
    name='hotsos',
    version='1.0.0',
    scripts=['scripts/hotsos'],
    packages=find_packages(include=['hotsos*']),
    install_requires=[
        'click',
        'pyyaml',
        'simplejson',
    ],
)

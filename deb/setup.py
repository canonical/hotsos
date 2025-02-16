from setuptools import setup, find_packages

setup(
    name='hotsos',
    packages=find_packages(include=['hotsos*']),
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
)

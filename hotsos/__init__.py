import os
if 'GIT_BUILD_VERSION' in os.environ:
    __version__ =  os.environ['GIT_BUILD_VERSION']
elif 'SNAPCRAFT_PART_BUILD' in os.environ:
    path =  os.environ['SNAPCRAFT_PART_BUILD']
    __version__ = open(os.path.join(path, 'git_build_version'))


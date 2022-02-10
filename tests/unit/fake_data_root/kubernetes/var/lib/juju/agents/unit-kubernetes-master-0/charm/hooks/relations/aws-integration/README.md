# Overview

This layer encapsulates the `aws-integration` interface communciation protocol
and provides an API for charms on either side of relations using this
interface.

## Usage

In your charm's `layer.yaml`, ensure that `interface:aws-integration` is
included in the `includes` section:

```yaml
includes: ['layer:basic', 'interface:aws-integration']
```

And in your charm's `metadata.yaml`, ensure that a relation endpoint is defined
using the `aws-integration` interface protocol:

```yaml
requires:
  aws:
    interface: aws-integration
```

For documentation on how to use the API for this interface, see:

* [Requires API documentation](docs/requires.md)
* [Provides API documentation](docs/provides.md) (this will only be used by the aws-integrator charm)

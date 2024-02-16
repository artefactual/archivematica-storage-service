# [Archivematica Storage Service]

By [Artefactual]

[![GitHub CI]][Test workflow]
[![codecov]][Archivematica Storage Service Codecov]

The Archivematica Storage Service is part of the Archivematica project.
Archivematica is a web- and standards-based, open-source application which
allows your institution to preserve long-term access to trustworthy, authentic
and reliable digital content. Our target users are archivists, librarians, and
anyone working to preserve digital objects.

The Storage Service is responsible for moving files to and from Archivematica
for processing and long-term storage. For more information, please see the
[Archivematica documentation].

You are free to copy, modify, and distribute the Archivematica Storage Service
with attribution under the terms of the AGPL license. See the [LICENSE] file for
details.

## Installation

* [Production installation]
* [Development installation]

## Resources

* [Website][Archivematica Storage Service]: User and administrator documentation
* [Wiki]: Developer facing documentation, requirements analysis and community
  resources
* [Issues]: Git repository used for tracking Archivematica issues and
  feature/enhancement ideas
* [User Google Group]: Forum/mailing list for user questions (both technical and
  end-user)
* [Paid support]: Paid support, hosting, training, consulting and software
  development contracts from Artefactual

## Contributing

Thank you for your interest!
For more details, please see the [contributing guidelines]

## Related projects

Archivematica consists of several projects working together, including:

* [Archivematica]: Main repository containing the user-facing dashboard, task
  manager MCPServer and clients scripts for the MCPClient
* [Storage Service]: This repository! Responsible for moving files to
  Archivematica for processing, and from Archivematica into long-term storage
* [Format Policy Registry]: Submodule shared between Archivematica and the
  Format Policy Registry (FPR) server that displays and updates FPR rules and
  commands

For more projects in the Archivematica ecosystem, see the [getting started] page.

[Archivematica Storage Service]: https://www.archivematica.org/
[Artefactual]: https://www.artefactual.com/
[GitHub CI]: https://github.com/artefactual/archivematica-storage-service/actions/workflows/test.yml/badge.svg
[Test workflow]: https://github.com/artefactual/archivematica-storage-service/actions/workflows/test.yml
[codecov]: https://codecov.io/gh/artefactual/archivematica-storage-service/branch/qa/0.x/graph/badge.svg?token=z1VcHtK8iw
[Archivematica Storage Service Codecov]: https://codecov.io/gh/artefactual/archivematica-storage-service
[Archivematica documentation]: https://www.archivematica.org/en/docs/
[LICENSE]: LICENSE
[Production installation]: https://www.archivematica.org/docs/latest/admin-manual/installation-setup/installation/installation/#installation
[Development installation]: https://github.com/artefactual/archivematica/tree/qa/1.x/hack
[Wiki]: https://www.archivematica.org/wiki/Development
[Issues]: https://github.com/archivematica/Issues
[User Google Group]: https://groups.google.com/forum/#!forum/archivematica
[Paid support]: https://www.artefactual.com/services/
[contributing guidelines]: CONTRIBUTING.md
[Archivematica]: https://github.com/artefactual/archivematica
[Storage Service]: https://github.com/artefactual/archivematica-storage-service
[Format Policy Registry]: https://github.com/artefactual/archivematica/tree/qa/1.x/src/dashboard/src/fpr
[getting started]: https://wiki.archivematica.org/Getting_started#Projects

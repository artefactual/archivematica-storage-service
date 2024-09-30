# Contributing

Thank you for considering a contribution to Archivematica!
This document outlines the change submission process for Archivematica, along
with our standards for new code contributions. Following these guidelines helps
us assess your changes faster and makes it easier for us to merge your
submission!

There are many ways to contribute: writing tutorials or blog posts about your
experience, improving the [documentation], submitting bug reports, answering
questions on the [mailing list], or writing code which can be incorporated into
Archivematica itself.

## Table of contents

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Submitting bugs](#submitting-bugs)
- [Submitting enhancement ideas](#submitting-enhancement-ideas)
- [Submitting code changes](#submitting-code-changes)
  - [Permalinks](#permalinks)
  - [Getting started](#getting-started)
  - [When to submit code for review?](#when-to-submit-code-for-review)
  - [Opening the pull request](#opening-the-pull-request)
  - [Discussion](#discussion)
  - [Cleaning up the commit history](#cleaning-up-the-commit-history)
  - [Stalled pull requests](#stalled-pull-requests)
- [Contributor's Agreement](#contributors-agreement)
  - [Why do I have to sign a Contributor's Agreement?](#why-do-i-have-to-sign-a-contributors-agreement)
  - [How do I send in an agreement?](#how-do-i-send-in-an-agreement)
- [Contribution standards](#contribution-standards)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Submitting bugs

If you find a security vulnerability, do NOT open an issue. Email
<info@artefactual.com> instead.

Issues can be filed using GitHub Issues in the [Archivematica Issues repo].
It is recommended to file issues there rather than in any of the
Archivematica-related code repositories. Artefactual staff also use GitHub
issues for any work they do on the Archivematica project.

You can also post in our [user] mailing list. A post to the mailing list is
always welcome, especially if you're unsure if it's a bug or a local problem!

Useful questions to answer if you're having problems include:

- What version of Archivematica and the Storage Service are you using?
- How was Archivematica installed? Package install, Ansible, etc?
- Was this a fresh install or an upgrade?
- What did you do to cause this bug to happen?
- What did you expect to happen?
- What did you see instead?
- Can you reproduce this reliably?
- If a specific Job is failing, what output did it produce? This is available
  by clicking on the gear icon.

## Submitting enhancement ideas

Similar to submitting bugs, you are welcome to submit ideas for enhancements or
new features in the [Archivematica Issues repo]. This is also where Artefactual
staff record upcoming enhancements when they have been sponsored for inclusion
either by Artefactual Systems or by a client.

Please feel free also to use the [Issues repo wiki] as a space for gathering and
collaborating on ideas. If you are not already a member of the
Archivematica repo (required for editing the wiki), file an issue there with
the title "Request membership."

## Submitting code changes

Every new feature and bugfix to a project is expected to go through code
review before inclusion. This applies both to developers at Artefactual and to
outside contributors.

Here's an outline of the contribution process:

1. File an issue in the
   [Archivematica Issues repo].
2. Fork the Artefactual project on GitHub, and commit your changes to a branch
   in your fork.
3. Open a pull request.
4. Back and forth discussion with developers on the branch.
5. Make any changes suggested by reviewers.
6. Repeat 3 and 4 as necessary.
7. Clean up commit history, if necessary.
8. Sign a Contributor's Agreement, if you haven't already.
9. Your branch will be merged!

### Permalinks

Issues can be enhanced by using GitHub's permalink features for [files] and
[code snippets].
Permalinks allow users to look back over old issues and pull requests and see
what the code looked like at a certain point in time. This can be useful where
lines may now have been added or removed but the topic of the conversation may
still be relevant or of interest to the reader.

### Getting started

So you have something to contribute to an Artefactual project. Great!

To install Archivematica, see our [development installation] instructions.

Artefactual uses [GitHub]'s pull request feature for code review. Every change
being submitted to an Artefactual project should be
submitted as a pull request to the appropriate repository. A branch being
submitted for code review should contain commits covering a related section of
code. Try not to bundle unrelated changes together in one branch; it makes
review harder.

If you're not familiar with forking repositories and creating branches in
GitHub, consult their [guide].

### When to submit code for review?

Your code doesn't have to be ready yet to submit for code review! You should
submit a branch for code review as soon as you want to get feedback on it.
Sometimes, that means submitting a feature-complete branch, but sometimes that
means submitting an early WIP in order to get feedback on direction. Don't be
shy about submitting early.

### Opening the pull request

GitHub has an [excellent] guide on using the pull request feature.

### Discussion

Discussion on pull requests is usually a back and forth process. Don't feel
like you have to make every change the reviewer suggests; the pull request is
a great place to have in-depth conversation on the issue.

Do make use of GitHub's line comment feature!

![Line comment]

By viewing the "Files changed", you can leave a comment on any line of the
diff. This is a great way to scope discussion to a particular part of a diff.
Any discussion you have in a specific part of the diff will also be
automatically hidden once a change is pushed that addresses it, which helps
keep the pull request page clear and readable.

Anyone can participate in code review discussions. Feel free to jump in if you
have something to contribute on another pull request, even if you're not the
one who opened it.

For more details about code review in particular, look at our
[code review guidelines].

### Cleaning up the commit history

Once code review is finished or nearly finished, and no further development is
planned on the branch, the branch's commit history should be cleaned up.
You can alter the commit history of a branch using git's powerful
[interactive rebase feature].

### Stalled pull requests

Pull requests that have been inactive for 60 days will be closed and properly
tagged using the "stalled" label. At that point, we prefer to continue the
discussion under the original GitHub issue that should be linked from the pull
request.

## Contributor's Agreement

In order for the Archivematica development team to accept any patches or code
commits, contributors must first sign this [Contributor's Agreement].
The Archivematica contributor's agreement is based almost verbatim on the
[Apache Foundation]'s individual [contributor license].

If you have any questions or concerns about the Contributor's Agreement,
please email us at <agreement@artefactual.com> to discuss them.

### Why do I have to sign a Contributor's Agreement?

One of the key challenges for open source software is to support a collaborative
development environment while protecting the rights of contributors and users
over the long-term.
Unifying Archivematica copyrights through contributor agreements is the best way
to protect the availability and sustainability of Archivematica over the
long-term as free and open-source software.
In all cases, contributors who sign the Contributor's Agreement retain full
rights to use their original contributions for any other purpose outside of
Archivematica, while enabling Artefactual Systems, any successor organization
which may eventually take over responsibility for Archivematica, and the wider
Archivematica community to benefit from their collaboration and contributions
in this open source project.

[Artefactual Systems] has made the decision and has a proven track record of
making our intellectual property available to the community at large.
By standardizing contributions on these agreements the Archivematica
intellectual property position does not become too complicated.
This ensures our resources are devoted to making our project the best they can
be, rather than fighting legal battles over contributions.

### How do I send in an agreement?

Please read and sign the [Contributor's Agreement] and email it to
<agreement@artefactual.com>.

Alternatively, you may send a printed, signed agreement to:

```text
Artefactual Systems Inc.
201 - 301 Sixth Street
New Westminster BC  V3L 3A7
Canada
```

## Contribution standards

For more information on contribution guidelines and standards, see the
CONTRIBUTING.md in the [Archivematica project].

[documentation]: https://github.com/artefactual/archivematica-storage-service-docs/
[mailing list]: https://groups.google.com/forum/#!forum/archivematica
[Archivematica Issues repo]: https://github.com/archivematica/Issues
[user]: https://groups.google.com/forum/#!forum/archivematica
[Issues repo wiki]: https://github.com/archivematica/Issues/wiki
[files]: https://help.github.com/articles/getting-permanent-links-to-files/
[code snippets]: https://help.github.com/articles/creating-a-permanent-link-to-a-code-snippet/
[development installation]: https://wiki.archivematica.org/Getting_started#Installation
[GitHub]: https://github.com/
[guide]: https://help.github.com/articles/fork-a-repo
[excellent]: https://help.github.com/articles/using-pull-requests
[Line comment]: https://i.imgur.com/FsWppGN.png
[code review guidelines]: https://github.com/artefactual/archivematica/blob/qa/1.x/code_review.md
[interactive rebase feature]: https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History
[Contributor's Agreement]: https://wiki.archivematica.org/images/e/e6/Archivematica-CLA-firstname-lastname-YYYY.pdf
[Apache Foundation]: http://apache.org
[contributor license]: http://www.apache.org/licenses/icla.txt
[Artefactual Systems]: http://artefactual.com
[Archivematica project]: https://github.com/artefactual/archivematica

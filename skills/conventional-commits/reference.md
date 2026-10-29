# Conventional Commits 1.0.0: the specification, the FAQ, the examples

Source: https://www.conventionalcommits.org/en/v1.0.0/ (key words MUST, SHOULD, MAY as in RFC 2119).

## Specification

1. Commits MUST be prefixed with a type, a noun such as `feat` or `fix`, followed by an OPTIONAL scope, an OPTIONAL `!`, and the REQUIRED terminal colon and space.
2. `feat` MUST be used when a commit adds a new feature.
3. `fix` MUST be used when a commit represents a bug fix.
4. A scope MAY follow the type: a noun describing a section of the codebase, in parentheses, `fix(parser):`.
5. A description MUST immediately follow the colon and space: a short summary of the change.
6. A longer body MAY follow the description, beginning one blank line after it.
7. The body is free-form and MAY consist of any number of newline-separated paragraphs.
8. One or more footers MAY follow the body after one blank line. Each footer MUST be a word token, then `: ` or ` #`, then a value, as in git's trailer convention.
9. A footer token MUST use `-` in place of whitespace, `Acked-by`, so the footer section can be told from a multi-paragraph body. `BREAKING CHANGE` is the exception and MAY be used as a token.
10. A footer value MAY contain spaces and newlines; parsing MUST stop at the next valid token and separator pair.
11. Breaking changes MUST be indicated in the type/scope prefix, or as a footer entry.
12. As a footer, a breaking change MUST be the uppercase `BREAKING CHANGE`, a colon, a space, and a description.
13. In the prefix, a breaking change MUST be a `!` immediately before the `:`. With `!`, the footer MAY be omitted and the description SHALL describe the breaking change.
14. Types other than `feat` and `fix` MAY be used, `docs: update ref docs`.
15. The units of Conventional Commits MUST NOT be treated as case sensitive by implementors, except `BREAKING CHANGE`, which MUST be uppercase.
16. `BREAKING-CHANGE` MUST be synonymous with `BREAKING CHANGE` as a footer token.

## The spec's examples

```
feat: allow provided config object to extend other configs

BREAKING CHANGE: `extends` key in config file is now used for extending other config files
```
```
feat!: send an email to the customer when a product is shipped
feat(api)!: send an email to the customer when a product is shipped
docs: correct spelling of CHANGELOG
feat(lang): add Polish language
```
```
chore!: drop support for Node 6

BREAKING CHANGE: use JavaScript features not available in Node 6.
```
```
fix: prevent racing of requests

Introduce a request id and a reference to latest request. Dismiss
incoming responses other than from latest request.

Remove timeouts which were used to mitigate the racing issue but are
obsolete now.

Reviewed-by: Z
Refs: #123
```
House rule: the two `feat!:` examples without a footer fail here; add `BREAKING CHANGE: ...`.

## FAQ, condensed

- **Initial development:** write messages as if the product were already released; someone will read them.
- **Case of the type:** either, but be consistent. Here: lowercase.
- **A commit that fits several types:** split it. Several types in one commit is a sign the commit is too big.
- **Does it slow iteration?** It discourages disorganised work, and makes moving fast across projects and people easier.
- **Does the type list limit what gets committed?** It encourages more small commits of the kinds that matter, like fixes. Teams may add types.
- **SemVer:** `fix` is PATCH, `feat` is MINOR, a breaking change is MAJOR whatever the type.
- **Extensions:** version your own extensions with SemVer.
- **Wrong type:** before merge or release, `git rebase -i` and amend. A type outside the spec is simply ignored by tools.
- **Must every contributor comply?** No; with squash merges the maintainer writes the final message.
- **Reverts:** not defined by the spec. Convention: `revert: <header of the reverted commit>` with a footer `Refs: <sha>`.

## Tools that read these messages

commitlint (`@commitlint/config-conventional`), semantic-release, release-please, conventional-changelog,
git-cliff, Versionize (.NET), GitVersion (mode `ContinuousDelivery` reads `+semver:` and `!`). All of them
need the header and the breaking-change signals to be exact; the body is for people.

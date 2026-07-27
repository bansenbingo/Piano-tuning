# Piano-tuning
Teddy's Undergraduate Graduation Thesis

## Commit branch rules

Enable the repository-managed Git hooks after cloning:

```sh
git config core.hooksPath .githooks
```

Commit subjects beginning with `0.x` or `0.x.x` (where each `x` is one or more
digits) are accepted only on `main`. Subjects beginning with `1.x` or `1.x.x`
are accepted only on `sandbox-audio-upload`.

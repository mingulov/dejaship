# Stored LLM Outputs

Generated fixture payloads will live under this versioned directory.

Expected layout:

```text
v1/
  <provider>/
    <model-alias>/
      <brief-id>.json
```

The default deterministic test suite should replay data from here instead of calling a live provider.

# render-prompt

Render the compile prompt exactly as it would be sent to the compile agent.

Useful for debugging — "what does the agent actually see?"

```bash
automaton wiki render-prompt
automaton wiki render-prompt --plugin-defaults
```

**Args:**
- `--plugin-defaults` — ignore the active wiki; render from plugin-shipped schema templates. Useful for previewing plugin changes before setup.

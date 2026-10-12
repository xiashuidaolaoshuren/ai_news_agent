# Implementation issues

A running log of changes that looked correct, passed tests, and still did not do what they said.

These are not design decisions (see [docs/adr](adr/)) and not milestones (see [docs/superpowers](superpowers/)). Each entry records one thing that bit us, the minimal reproduction, the cause, and the rule that prevents it.

Add an entry when you find something that a test suite and a quick look both missed. Keep entries short and verified: if a claim can be checked with a command, include the command and its real output.

## Index

| # | Issue | Area |
|---|---|---|
| [0001](#0001-vue-scoped-css-discards-the-rest-of-a-selector-containing-global) | Vue scoped CSS discards the rest of a selector that contains `:global()` | frontend / CSS |

---

## 0001 Vue scoped CSS discards the rest of a selector containing `:global()`

**Status:** fixed in `7265e3b`. Introduced in `4781793` (8B T5).
**Where:** `frontend/src/components/shell/ChatHead.vue`
**Versions:** Vue 3.5.43, `@vue/compiler-sfc` 3.5.43, Vite 8.3.4.

### Symptom

The chat-head theme button was meant to show a moon in light mode and a sun in dark mode. In light mode it was correct. In dark mode it kept showing the moon and the sun never appeared. Nothing else looked broken.

### What the code did

The button held both icons and swapped them with CSS:

```css
.theme-btn .ic-sun {
  display: none;
}

:global([data-theme='dark']) .theme-btn .ic-moon {
  display: none;
}

:global([data-theme='dark']) .theme-btn .ic-sun {
  display: block;
}
```

### Reproduction

Ask Vue's own compiler what that style block compiles to. From `frontend/`:

```js
import { compileStyle } from '@vue/compiler-sfc'

const source = `
.theme-btn .ic-sun { display: none; }
:global([data-theme='dark']) .theme-btn .ic-moon { display: none; }
:global([data-theme='dark']) .theme-btn .ic-sun { display: block; }
`

console.log(compileStyle({ source, filename: 'ChatHead.vue', id: 'data-v-abc123', scoped: true }).code)
```

Observed output:

```css
.theme-btn .ic-sun[data-v-abc123] {
  display: none;
}
[data-theme='dark'] {
  display: none;
}
[data-theme='dark'] {
  display: block;
}
```

Two things happened to the `:global()` rules, and neither was intended:

1. `.theme-btn .ic-moon` and `.theme-btn .ic-sun` were **deleted from the selector**. The rules became plain global rules on `[data-theme='dark']`, which matches `<html>`.
2. **No scope attribute was added at all.** The rules are unscoped, not scoped.

### Cause

In `@vue/compiler-sfc`'s scoped-style plugin (`style/pluginScoped.ts`), the `:global` branch is:

```js
// global: replace with inner selector and do not inject [id].
// ::v-global(.foo) -> .foo
if (value === ':global' || value === '::v-global') {
  selector.replaceWith(n.nodes[0])
  return false
}
```

`n.nodes[0]` is the pseudo's inner **selector**, not a single node. So `selector.replaceWith(...)` swaps the entire selector out of its parent and puts the inner selector in its place. The selector object the function keeps mutating is now detached, so the scope attribute it injects afterwards never reaches the output, and the `return false` stops the walk before any later node can be recorded as the anchor.

The intended reading of that comment is "the whole rule is global". Vue's own documentation only shows `:global()` used as the entire selector. Sharing a selector between `:global()` and normal parts is not supported, and it fails silently: no warning, no compile error, no test failure.

The result is not "the scope attribute lands in the wrong place", it is "**everything except the `:global()` part is thrown away**". The same happens wherever `:global()` sits in the selector:

| Source (inside `<style scoped>`) | Compiled |
|---|---|
| `.theme-btn .ic-sun { display: none }` | `.theme-btn .ic-sun[data-v-hash] { display: none }` |
| `:global([data-theme='dark']) .theme-btn .ic-moon { … }` | `[data-theme='dark'] { … }` |
| `[data-theme='dark'] .theme-btn :global(.ic-moon) { … }` | `.ic-moon { … }` |
| `.theme-btn :deep(.ic-moon) { … }` | `.theme-btn[data-v-hash] .ic-moon { … }` |
| `:global(.red) { color: red }` | `.red { color: red }` |

Only the last row is the documented, working use. `:deep()` behaves correctly and keeps a scope anchor.

This is worth calling out because the pattern reads as reasonable. It looks like "apply this scoped rule only in dark mode", which is the intent, and Vue 3 accepts it without a warning or error. Nothing in the toolchain tells you the selector was rewritten.

### Worst case: nearly blanked the page

Both surviving rules target `[data-theme='dark']` with identical specificity, so the later one wins and `<html>` computed `display: block`. That is why the only visible damage was the wrong icon.

Had the order been reversed, or had only the `display: none` rule existed, the same mistake would have set `display: none` on the root element and blanked the entire application in dark mode. Verified in a browser:

```
html { display: none }  ->  htmlDisplay: "none", bodyHeight: 0
```

So a CSS typo in a component's scoped style can silently become a whole-app failure, and the version that shipped happened to land on the harmless side of the cascade.

### Fix

Stop using the cascade for a two-state icon. Derive it from state and render one icon:

```ts
/** Moon in light mode, sun in dark — same affordance as the prototype head toggle. */
const themeIcon = computed(() => (themeStore.theme === 'dark' ? 'sun' : 'moon'))
```

```html
<AppIcon :name="themeIcon" />
```

Fixed in `7265e3b` (`fix(frontend): drive chat head theme icon from store`).

### Why it was missed

The change was reported as working. The verification behind that report was:

- A CDP probe of the light-mode state only (`headSun: "none"`, `headMoon: "block"`), which confirmed exactly the half that was already correct.
- Dark mode was judged by looking at a 16px glyph in a screenshot, where a moon and a sun are easy to confuse.

The bug survived because the two halves were checked with different levels of rigour, and only the half using `:global()` was broken. Re-running the same probe after the theme toggle would have caught it immediately.

### Rule

- `:global()` is **whole-selector only**. Do not combine it with other parts of a selector in scoped CSS.
- To style into a child component, use `:deep()`. To write a rule that must stay unscoped, put it in a global stylesheet (`frontend/src/styles/tokens.css`, `frontend/src/styles/controls.css`) or in a separate unscoped `<style>` block, which is where the prototype's theme rules live.
- Do not drive state changes through scoped CSS when component state can drive them directly. Bind the view to state.
- When a rule is claimed to work, measure it in every state it is supposed to cover, not just the first one.

### Check

Any CSS in a `<style scoped>` block containing `:global(` is suspect. Confirm what it compiles to before trusting it:

```bash
cd frontend
node --input-type=module -e "import { compileStyle } from '@vue/compiler-sfc'; console.log(compileStyle({ source: ':global(.a) .b { color: red }', filename: 'x.vue', id: 'data-v-x', scoped: true }).code)"
```

If the output is a selector you did not write, the rule is not doing what you think. The command above prints `.a { color: red }`: the trailing `.b` is gone.

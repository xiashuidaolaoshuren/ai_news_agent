# Implementation Issues

A learning log of bugs and surprises found while building AI News Research Agent. Each entry records what went wrong, why, and what we changed so the lesson sticks.

Entry 1 came from the milestone 8B frontend work (T5, sidebar and chat head), and was found by a reviewer rather than by a test: the change had already been reported as working. Where [docs/adr](adr/) records decisions and [docs/superpowers](superpowers/) records milestones, this file records faults.

Add an entry when something passes its tests and still does not do what it says. Reproduce it against the live code, not from the spec.

## Index

| # | Issue | Area |
|---|---|---|
| [1](#1-vue-scoped-css-silently-drops-the-rest-of-a-selector-containing-global) | Vue scoped CSS silently drops the rest of a selector containing `:global()` | frontend / CSS |
| [2](#2-theme-reveal-lags-from-the-second-toggle-because-a-finished-fill-both-animation-is-never-cancelled) | Theme reveal lags from the second toggle because a finished `fill: 'both'` animation is never cancelled | frontend / View Transitions |

---

## 1. Vue scoped CSS silently drops the rest of a selector containing :global()

**When:** 8B T5 fix pass (chat head theme icon), 12 Oct 2026. Fix landed in `7265e3b`; the bug came in with `4781793`.  
**Area:** `frontend/src/components/shell/ChatHead.vue` (scoped `<style>`, theme button)  
**Symptom:** The chat-head theme button showed a moon in light mode, which was correct, and kept showing a moon in dark mode, where a sun was expected. Nothing else looked wrong.

### What we saw

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

Asking Vue's own compiler what that block produces (`compileStyle` from `@vue/compiler-sfc` 3.5.43, `scoped: true`, `id: 'data-v-abc123'`):

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

1. `.theme-btn .ic-moon` and `.theme-btn .ic-sun` were **deleted from the selector**. Both rules became plain global rules on `[data-theme='dark']`, which matches `<html>`.
2. **No scope attribute was added at all.** Those rules are unscoped, not scoped.

Both surviving rules have identical specificity, so the later `display: block` won and `<html>` computed `display: block`. That is why the only visible damage was the wrong icon. Had the two rules been written in the opposite order, the same mistake would have set `display: none` on the root element — measured in a browser, `html { display: none }` gives `bodyHeight: 0`, a blank application.

### Root cause

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

The result is not "the scope attribute lands in the wrong place", it is "everything except the `:global()` part is thrown away". The same happens wherever `:global()` sits in the selector:

| Source (inside `<style scoped>`) | Compiled |
|---|---|
| `.theme-btn .ic-sun { display: none }` | `.theme-btn .ic-sun[data-v-hash] { display: none }` |
| `:global([data-theme='dark']) .theme-btn .ic-moon { … }` | `[data-theme='dark'] { … }` |
| `[data-theme='dark'] .theme-btn :global(.ic-moon) { … }` | `.ic-moon { … }` |
| `.theme-btn :deep(.ic-moon) { … }` | `.theme-btn[data-v-hash] .ic-moon { … }` |
| `:global(.red) { color: red }` | `.red { color: red }` |

Only the last row is the documented, working use. `:deep()` behaves correctly and keeps a scope anchor.

The pattern reads as reasonable, which is why it was written: it looks like "apply this scoped rule only in dark mode". Nothing in the toolchain says the selector was rewritten.

### Fix

Stop using the cascade for a two-state icon. Derive it from state and render one icon:

```ts
/** Moon in light mode, sun in dark — same affordance as the prototype head toggle. */
const themeIcon = computed(() => (themeStore.theme === 'dark' ? 'sun' : 'moon'))
```

```html
<AppIcon :name="themeIcon" />
```

Committed as `7265e3b` (`fix(frontend): drive chat head theme icon from store`).

No automated regression covers the icon choice. `frontend/src/stores/theme.test.ts` covers the store, but the icon mapping is a template binding, so the guards are the rule below and the compile check.

### Lesson

- `:global()` is **whole-selector only**. Do not combine it with other parts of a selector in scoped CSS. To reach into a child component use `:deep()`, which keeps a scope anchor.
- To write a rule that must stay unscoped, put it in a global stylesheet (`frontend/src/styles/tokens.css`, `frontend/src/styles/controls.css`) or in a separate unscoped `<style>` block. That is where the prototype's theme rules live, and it is why the port broke when the same rules moved into a scoped block.
- Do not drive state changes through scoped CSS when component state can drive them directly. A computed property cannot be defeated by a compiler rewrite.
- A silent rewrite is more dangerous than an error. This one turned a two-line visibility toggle into a rule targeting the root element, and the only reason it did not blank the whole app was the order of two rules in the same block.
- The change was reported as working because the two halves were verified to different standards: light mode was measured with a CDP probe, dark mode was judged by eye from a 16px glyph in a screenshot. Measure every state a rule is supposed to cover, and measure rather than look when measuring is cheap.

Any CSS in a `<style scoped>` block containing `:global(` is suspect. Confirm what it compiles to before trusting it:

```bash
cd frontend
node --input-type=module -e "import { compileStyle } from '@vue/compiler-sfc'; console.log(compileStyle({ source: ':global(.a) .b { color: red }', filename: 'x.vue', id: 'data-v-x', scoped: true }).code)"
```

The command above prints `.a { color: red }`: the trailing `.b` is gone. If the output is a selector you did not write, the rule is not doing what you think.

---

## 2. Theme reveal lags from the second toggle because a finished fill: 'both' animation is never cancelled

**When:** fidelity follow-up after U7, Nov 2026. Fixed in the working tree on `features/remaining-followup` (not committed when this entry was written).  
**Area:** `frontend/src/stores/theme.ts` (`runSetTheme`, the circular clip-path reveal)  
**Symptom:** With hardware acceleration on, the first theme switch was smooth and every later one lagged. The prototype served in the same Chrome behaved the same way. The OpenDesign desktop app stayed smooth.

### What we saw

An earlier pass blamed software rendering (Chrome was on "Microsoft Basic Render Driver"). That was a real problem, but turning acceleration on did not remove the lag, so it was not the whole story. The cheap code fixes from that pass (no `theme-snap` before the capture, a synchronous update callback, a CSS-driven icon) shortened the first frame and changed nothing for repeat toggles.

The signal was invisible to the usual measurement. `requestAnimationFrame` pacing stayed smooth on every toggle, so main-thread frame timing showed nothing. A GPU-side trace did. On Chrome 159 with a clean profile (no extensions, RTX 3070 Ti, 1600×900 at DPR 1.5), counting `DrawFrame` events over each 800 ms window:

| Toggle | Leftover animations before the click | `DrawFrame` per reveal |
|---|---|---|
| 1 | 0 | 39 to 40 |
| 2 | 1 | 39 to 40 |
| 3 | 2 | **6 to 7** |
| 4 | 2 | **6 to 7** |

Cancelling every pseudo-element animation by hand before each click gave 39 `DrawFrame` on all four toggles, in both the host and the prototype. That isolated the cause.

### Root cause

The reveal is started with:

```ts
root.animate(
  { clipPath: [...] },
  { duration: 600, easing: '...', fill: 'both',
    pseudoElement: '::view-transition-new(root)' /* or old(root) */ },
)
```

and the returned `Animation` was dropped. `fill: 'both'` keeps a finished animation alive and applying its end state, so each toggle left one more entry in `document.getAnimations()`, one per pseudo-element (`new(root)` for grow, `old(root)` for shrink). The page never went back to zero.

Once a leftover animation targeted the same pseudo-element, Chrome stopped running the new reveal's clip-path on the compositor and drove it from the main thread instead. The reveal then drew about 6 frames in 600 ms. The next toggles inherit the leftovers, so the lag is permanent for the life of the page.

The prototype ships the same code, so it has the same bug. OpenDesign's preview is smooth most likely because it reloads the document between runs and so drops the leftovers; this was not verified.

### Fix

Keep the animation and cancel it when its transition finishes, before the "is this still the current transition" guard, so a reveal cut short by a newer click is also released:

```ts
let reveal: Animation | undefined
void vt.ready.then(() => { reveal = root.animate(...) })

void vt.finished.finally(() => {
  reveal?.cancel()
  if (themeViewTransition !== vt) return
  ...
})
```

`fill: 'both'` stays. Without it the shrink flashes the old theme for one frame between the animation ending and the pseudo-elements being removed. Cancelling after `finished` is invisible because the pseudo-elements are already gone.

After the fix, six toggles in a row each draw 39 `DrawFrame` with 0 leftover animations. Regression test: "cancels each reveal animation once its transition finishes" in `frontend/src/stores/theme.test.ts` (it failed before the change).

### Lesson

- An animation created with `Element.animate()` and `fill: 'forwards'` or `'both'` does not go away when it ends. Keep the handle and call `cancel()` (or `commitStyles()` then `cancel()`) once the end state is owned by something else.
- A leftover animation can silently demote later animations on the same target from the compositor to the main thread. The visible result is jank with no error, and only some measurements see it.
- Measure the thread the animation actually runs on. `requestAnimationFrame` deltas look at the main thread and said "smooth" while the GPU path was drawing a sixth of the frames. Use a trace (`DrawFrame`, `DroppedFrame`) or compare `document.getAnimations()` before and after each run.
- Test repeat runs, not just the first. Every earlier check toggled once and passed.
- "Works in the design tool, lags in the browser" was a hint that something stateful was being reset by the tool, not that the browser was slower. Ask what differs between a fresh and a long-lived document.

Quick check in the console after a few toggles; the result should stay at 0:

```js
document.getAnimations().filter(a => a.effect?.pseudoElement).length
```

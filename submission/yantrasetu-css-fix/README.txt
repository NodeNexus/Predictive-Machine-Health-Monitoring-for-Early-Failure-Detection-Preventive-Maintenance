YantraSetu CSS fix (tested; CSS only, no HTML or JS changes)

Fixes
- Page was wider than the screen on phones (463 px on a 390 px phone) - no horizontal overflow now at 320/360/390/768/1100 px.
- Desktop header no longer squashes the "Test Interactive Console" button.
- Phone menu is a swipeable row instead of hidden.

To deploy (repo NodeNexus/YantraSetu):
  Option 1: replace public/assets/css/style.css with style.css from this folder, commit, push to main.
  Option 2: from the repo root run:  git apply path/to/style-fix.patch
Render redeploys automatically on push to main.

# Thermal Dataset Audit — Induction Motor Thermal Datasets

**Scope: inspection only.** No model was trained, no existing IDEA LAB code (thermal pipeline, dashboard, anomaly engine, demo behavior) was modified. All findings below were verified against the actual local files (image headers, raw bytes, visual inspection) — not inferred from the dataset webpages.

---

## 1. Dataset locations

Both datasets were downloaded as zip files sitting at the **project root** (`c:\Users\VNAV-PC\Desktop\MECHANICAL\`), **not** inside `DATASET/`:

- `Induction Motor-Thermal Images.zip` (57.5 MB) — Mendeley DOI `pymtdhfzbj`
- `Thermal image of equipment (Induction Motor) + 40 Ground Truths added.zip` (10.9 MB) — Mendeley DOI `m4sbt8hbvk`

Both are nested archives (a zip containing another zip, and a zip containing two `.rar` files + a PDF). For this audit they were extracted **in place at the project root** into clearly-named staging folders (not moved anywhere, not merged into `DATASET/`, and now excluded via `.gitignore` so they are never accidentally committed):

- `_thermal_audit_ds1/Induction Motor-Thermal Images/` — Dataset 1
- `_thermal_audit_ds2/IR-Motor-bmp/` and `_thermal_audit_ds2/40_GT_with_References/` — Dataset 2

No reorganization into the existing `DATASET/` structure or dataset-scanner registration was performed — that is a decision for the next step, not this audit.

---

## 2. Directory structure

**Dataset 1** (`_thermal_audit_ds1/Induction Motor-Thermal Images/`):
```
HFL/  (112 files)
HML/  (82 files)
HNL/  (90 files)
CFL/  (49 files)
CML/  (79 files)
CNL/  (76 files)
```
All 488 files are `.jpg`. No CSV/JSON/XML/TXT/README/PDF of any kind exists anywhere in this archive — confirmed by a full file-type scan (488 files, 100% `.jpg`, zero other extensions).

**Dataset 2** (`_thermal_audit_ds2/`):
```
IR-Motor-bmp/
  A&B50/ (38)   A&C&B10/ (31)   A&C&B30/ (42)   A&C10/ (31)
  A&C30/ (38)   A10/ (34)   A30/ (37)   A50/ (35)
  Fan/ (28)   Noload/ (25)   Rotor-0/ (30)
40_GT_with_References/
  40_GT_Induction-motor.txt
  Subset_40_Thermal_GT/  (40 image pairs: NNN.bmp + NNN.tiff)
Readme_InductionMotor.pdf
```
All `IR-Motor-bmp` files are `.bmp` (369 total, matching the README's stated total exactly). The 40-ground-truth subset has 40 `.bmp`/`.tiff` pairs (80 files). A real, informative README PDF exists (`Readme_InductionMotor.pdf`).

**Duplicates found:** none in Dataset 1 (exact MD5 check, 0 collisions across 488 files). Dataset 2's `IR-Motor-bmp` has **one exact byte-for-byte duplicate pair**: `A30/152.bmp` == `A30/153.bmp` (within the same class, not cross-class).

**No train/test/validation split exists in either dataset** — confirmed by directory search; only class-named folders are present.

---

## 3. Image inspection (observed, via OpenCV header/pixel inspection)

| | Dataset 1 | Dataset 2 (`IR-Motor-bmp`) | Dataset 2 (40-GT `.tiff`) |
|---|---|---|---|
| Format | JPEG | BMP | TIFF |
| Count | 488 | 369 | 40 |
| Resolution | 640×480 | 320×240 | 320×240 |
| Channels | 3 (color) | 3 (color) | 3 (color) |
| Bit depth | 8-bit/channel | 8-bit/channel | 8-bit/channel |
| Pixel range observed | 0–255 | 0–~223 (varies per image) | 0–255, but only a **binary** silhouette (see below) |

Filenames in Dataset 1 follow the pattern `FLIRnnnn.jpg` — a genuine FLIR camera export naming convention (not a generic camera or a screenshot).

**Radiometric/metadata check (Dataset 1):** raw-byte inspection of sample JPEGs found the literal strings `Teledyne FLIR`, `FLIR C5` (camera model), the `FFF\x00` **FLIR File Format container signature**, and a reference to the `/FLIR/usr/etc/iron.pal` color palette file — all consistent with a genuine FLIR-format image that embeds a proprietary metadata/raw-data container. This marker was found consistently in a sample from **all 6 classes**. I did **not** attempt to parse or extract the embedded raw radiometric array (that requires a dedicated tool such as ExifTool's `-FLIR:all` or a Python library like `flyr`/`flirimageextractor`, neither of which is installed — extraction was explicitly out of scope for this audit).

**Visual confirmation (Dataset 1):** three sample images (one each from HFL, CFL, CNL) were rendered and visually inspected. Every one shows a **burned-in, human-readable spot-temperature readout** in the top-left corner (e.g. "38.0°C", "47.1°C", "26.4°C" — three different real values across three different images) next to a crosshair icon, plus a FLIR logo watermark. **Important caveat, also observed visually:** the crosshair/readout appears to sit at a fixed on-screen position, not dynamically on the hottest pixel — in the CFL and CNL samples the crosshair is visibly *not* on the brightest (hottest-looking) region of the frame. This single spot-reading must not be assumed to equal the image's maximum temperature or the fault-region temperature.

**Radiometric/metadata check (Dataset 2):** the identical raw-byte search (`FLIR`, `FFF`, `Planck`, `Exif`) found **none** of these markers in the BMP files. Visual inspection of a sample image (Rotor-0 class) shows a colorized thermal palette (purple→orange→yellow) with **no burned-in temperature value, no scale bar/legend, and no camera watermark**.

**Dataset 2's 40-GT `.tiff` files are NOT temperature data.** Visual inspection (converted to PNG and viewed) shows each `.tiff` is a **binary silhouette mask** — a white region on a solid black background, matching the shape/position of the motor body in the corresponding `.bmp`. Pixel analysis confirms: not identical to the BMP (100% of pixels differ from the source image), each has 54–84 unique grayscale values with non-equal color channels (i.e. it is a rendered/anti-aliased mask, not a flat binary array), and it uses the full 0–255 range. This is a **region-of-interest / motor-silhouette segmentation mask**, one per source image, filename-matched (`017.bmp` ↔ `017.tiff`).

---

## 4. Label inspection

### Dataset 1: `HFL, HML, HNL, CFL, CML, CNL`

**No documentation file of any kind accompanies this dataset locally** — the archive contains only 488 JPEGs, nothing else. The class meanings below are therefore an **inference**, not a confirmed fact, based on: (a) the letter structure (`H`/`C` × `F`/`M`/`N` × `L`), (b) the images themselves showing a running induction motor under visibly different thermal states, and (c) the FLIR sequence numbers being cleanly, non-overlapping partitioned by class (see §8) — consistent with one continuous recording session per labelled condition.

| Label | Plausible meaning (INFERRED, not confirmed) | Count |
|---|---|---|
| HFL | Healthy — Full Load | 112 |
| HML | Healthy — Medium Load | 82 |
| HNL | Healthy — No Load | 90 |
| CFL | (Some) fault condition — Full Load | 49 |
| CML | (Some) fault condition — Medium Load | 79 |
| CNL | (Some) fault condition — No Load | 76 |

**What is directly observable, not inferred:** two top-level groups exist (`H*` and `C*`) and each has three sub-conditions (`*FL`, `*ML`, `*NL`). Whether `C` specifically means "corroded bearing," "current fault," or another single specific fault type **cannot be determined from local files** — no documentation states it. **This must be resolved from the dataset's published paper/webpage before being used for training**, not assumed.

### Dataset 2: directly documented via `Readme_InductionMotor.pdf`

This dataset's labels ARE directly documented, and folder counts were cross-checked arithmetically against the README's Table 3 — **all 11 categories reconcile exactly** (see table below), which gives high confidence in this mapping:

| Folder | README category | Meaning | Count |
|---|---|---|---|
| `Noload` | Healthy | No fault, no load | 25 |
| `Rotor-0` | Rotor | Stuck-rotor fault | 30 |
| `Fan` | Cooling | Cooling-fan failure | 28 |
| `A50` | 50%-stator, 1-Phase | Stator short-circuit, phase A, 50% severity | 35 |
| `A&B50` | 50%-stator, 2-Phase | Stator short-circuit, phases A+B, 50% severity | 38 |
| `A30` | 30%-stator, 1-Phase | Stator short-circuit, phase A, 30% severity | 37 |
| `A&C30` | 30%-stator, 2-Phase | Stator short-circuit, phases A+C, 30% severity | 38 |
| `A&C&B30` | 30%-stator, 3-Phase | Stator short-circuit, all 3 phases, 30% severity | 42 |
| `A10` | 10%-stator, 1-Phase | Stator short-circuit, phase A, 10% severity | 34 |
| `A&C10` | 10%-stator, 2-Phase | Stator short-circuit, phases A+C, 10% severity | 31 |
| `A&C&B10` | 10%-stator, 3-Phase | Stator short-circuit, all 3 phases, 10% severity | 31 |

**Total: 369**, matching the README exactly. `A`/`B`/`C` denote the three stator phases (standard 3-phase motor phase labeling); the percentage is the documented, directly-labelled short-circuit severity — this is a real, quantified severity measure, not an invented bucket.

---

## 5. Fault / condition information — directly labelled vs. inferred

| Question | Dataset 1 | Dataset 2 |
|---|---|---|
| Healthy vs. faulty? | Directly labelled (H vs. C) | Directly labelled (Noload vs. all others) |
| Specific fault type? | **Not confirmed locally** (no docs) | Directly labelled: stator short-circuit (by phase + %), stuck rotor, cooling-fan failure |
| Severity? | Not present | Directly labelled (10/30/50% short-circuit rate) — real measured severity, not invented |
| Load condition? | Inferred from `F/M/N` suffix (Full/Medium/No load) — plausible but unconfirmed | Not varied — README's Table 1 states fixed equipment spec (2800 RPM, 1.1kW), no per-image load variation documented |
| RPM? | Not present | Fixed at 2800 RPM for all images (equipment spec, not a per-image variable) |
| Bearing condition? | Not present in either dataset | Not present |
| Environment temperature? | Not present | Documented as a constant 23°C ambient (not per-image) |

No severity buckets such as "healthy/moderate/risky/critical" exist in either dataset and none should be invented — Dataset 2's real severity axis is the documented short-circuit percentage; Dataset 1 has no severity axis at all beyond the binary healthy/fault class split.

---

## 6. Temperature information

| | Category | Evidence |
|---|---|---|
| **Dataset 1** | **C (metadata/burned-in temperature) confirmed; A/B (full radiometric array) plausible but unverified** | Visible burned-in spot-temperature readout confirmed on 3/3 sampled images across 3 classes, with genuinely different real values (38.0°C, 47.1°C, 26.4°C). Raw-byte evidence of an embedded FLIR File Format (FFF) container was found consistently across all 6 classes, which in genuine FLIR exports typically carries a full per-pixel raw radiometric layer plus Planck calibration constants — **this was not extracted or verified in this audit**; only the presence of the container signature was confirmed. |
| **Dataset 2 (`IR-Motor-bmp`)** | **D (colorized intensity only)** | No FLIR/Exif/Planck markers found in raw bytes; no burned-in temperature text visible; no scale bar/legend visible in the sample viewed. Camera used (per README) is radiometric-capable (Dali-tech T8, −20 to 650°C range), but the **exported BMP format itself carries no evidence of retained calibration** — it is an 8-bit, 3-channel colorized snapshot. |
| **Dataset 2 (40-GT `.tiff`)** | **F (not temperature data at all)** | Confirmed to be binary ROI/silhouette masks, not thermal or temperature data of any kind. |

**If Dataset 1's embedded radiometric data needs to be reconstructed/extracted later, the documented path is:** use a FLIR-aware parser (e.g., ExifTool's `-FLIR:all` output, or the Python `flyr` / `flirimageextractor` packages) to pull the raw thermal frame + calibration parameters (Planck R1/R2/B/F/O, emissivity, reflected/atmospheric temperature, distance) out of the JPEG's embedded FFF container, then apply the Planck-law inverse to convert raw sensor counts to °C per pixel. **This reconstruction was explicitly not implemented in this audit.**

---

## 7. Annotations / ground truth (Dataset 2's "40 Ground Truths")

- **Format:** paired raster images — `NNN.bmp` (source thermal image, colorized, 320×240) + `NNN.tiff` (mask, same resolution).
- **What is annotated:** a single region per image — visually, the silhouette/outline of the motor body (or the visible component in frame) against a black background.
- **Not** bounding boxes, not polygon coordinate lists, not a class-label file, not multi-region/multi-class masks (only two pixel classes observed: foreground/background).
- The accompanying `40_GT_Induction-motor.txt` file exists alongside `Subset_40_Thermal_GT/` — its content was not further parsed in this audit beyond confirming its presence; it may contain per-image references or citations (the archive is literally named "40_GT_**with_References**"), not necessarily annotation coordinates. **This should be read before assuming it contains anything beyond citation/reference text.**
- The 40 GT filenames sample across multiple naming patterns seen elsewhere in the dataset (plain numbers like `017`, `f086`-style, `r050`-style) — suggesting this 40-image subset was drawn from across multiple condition folders, not from one single class. This was not cross-referenced file-by-file against the class folders in this audit.

**This is a segmentation-style ROI ground truth, not a fault-detection or fault-localization annotation** — there is no evidence the mask distinguishes a "fault region" from a "normal region"; it appears to simply delineate the equipment from its background.

---

## 8. Duplicates / leakage risk

- **Dataset 1:** zero exact duplicate files. However, a real and important structural risk was found: the FLIR sequence numbers are **cleanly, non-overlapping partitioned by class** with no interleaving:

  | Class | Sequence range |
  |---|---|
  | CNL | 0395–0470 |
  | CML | 0471–0549 |
  | CFL | 0550–0598 |
  | HNL | 0599–0688 |
  | HML | 0689–0770 |
  | HFL | 0771–0882 |

  This means each class was captured as **one continuous recording block**, not sampled across independent sessions. Consecutive frames within a class are very likely to be near-duplicate (same motor, same camera position, same background, seconds apart). **A naive random train/test split within a class risks severe leakage** — the model could learn to recognize the specific background/session rather than the thermal fault signature. Any split must be done by holding out entire contiguous blocks/sessions, not random per-image sampling.
- **Dataset 2:** one exact duplicate pair within the same class (`A30/152.bmp` == `A30/153.bmp`) — a minor data-quality issue (effectively 368 unique images, not 369), not a cross-class leakage issue.
- **Neither dataset has a predefined train/test split** — this must be designed deliberately (see above) before any training work, not left to a default random split.

---

## 9. Data quality (sample-based visual + programmatic check)

- No corrupted or unreadable images encountered among the samples opened (one per class in each dataset, plus the 3 fully visually inspected Dataset-1 samples and 2 Dataset-2 samples).
- No blank/all-black or all-white images observed in the samples checked.
- No visible-light (non-thermal) images or screenshots found mixed in — every sample opened was a genuine thermal-palette image.
- Resolution is **consistent within each dataset** (640×480 throughout Dataset 1; 320×240 throughout Dataset 2, including the 40-GT subset) — no inconsistent resolutions observed in the files checked.
- Dataset 1's images legitimately contain "extra" content beyond the thermal scene itself (on-screen crosshair, temperature text, FLIR logo) that a training pipeline would need to either crop out or explicitly account for — leaving it in as-is could let a model key on the overlay rather than the motor.
- **Filenames are not misleading** in either dataset — Dataset 1's FLIR-numbered files and Dataset 2's class-coded filenames both matched their folder's documented/inferred condition in every sample checked.
- This was a **sample-based** check (a handful of images per class, not all 488 + 369 + 40 files) — a full corrupted-file/blank-image sweep across every file was not performed in this audit.

---

## 10. Visual sample report

Representative samples were rendered and visually inspected (not saved into the repository — this was an ephemeral inspection step, per "use it only for inspection, do not modify the dataset"):

- Dataset 1, HFL (healthy?, full load?): motor visibly warm through the body, hot fan/coupling region, spot reading 38.0°C.
- Dataset 1, CFL (fault?, full load?): motor visibly warmer overall, very hot fan/coupling region, spot reading 47.1°C.
- Dataset 1, CNL (fault?, no load?): motor body itself the hottest region, spot reading 26.4°C.
- Dataset 2, Rotor-0: colorized purple-to-yellow palette, motor body clearly delineated from cool background, no overlay/legend.
- Dataset 2, 40-GT pair (`017`): source BMP shows the motor in-frame; paired TIFF shows a clean binary silhouette mask of the same motor's outline.

A full contact-sheet grid image was not generated as a saved artifact in this audit (would require picking a location and format decision better made alongside the next concrete task); the above individual samples were sufficient to answer the audit's actual questions.

---

## 11. Supported ML tasks

| Task | Dataset 1 | Dataset 2 |
|---|---|---|
| A. Image classification | **Supported.** Input=JPEG, target=6-class folder label. Limitation: exact class semantics beyond H/C split are unconfirmed; leakage risk from session-blocked sequence numbers (§8) must be addressed in the split design. | **Supported, well.** Input=BMP, target=11-class folder label with a documented, cross-checked mapping. Same "no predefined split" caveat, but no session-blocking risk was found (folders are independent condition captures, not confirmed to be one continuous sequence each — this was not specifically checked for Dataset 2 the way it was for Dataset 1's FLIR numbering). |
| B. Object detection | **Not supported** — no bounding boxes exist in either dataset. |
| C. Segmentation | **Not supported** for Dataset 1 (no masks). **Supported only for the 40-image GT subset** of Dataset 2, and only as motor-vs-background silhouette segmentation — not fault-region segmentation (no evidence the mask marks a fault location). |
| D. Anomaly detection | **Plausible** using only the "healthy" classes (Dataset 1's `H*`, Dataset 2's `Noload`) as the normal-only training set, matching the architecture already used elsewhere in IDEA LAB. Limitation: very few healthy images (90+82+112=284 for Dataset 1; just 25 for Dataset 2). |
| E. Severity classification | **Not supported** for Dataset 1 (no severity label exists, only healthy/fault). **Directly supported** for Dataset 2's stator-fault subset (10/30/50% is a real ordinal severity target) — though the rotor/fan/healthy classes fall outside that severity axis. |
| F. Regression | **Not directly supported** by folder labels alone in either dataset (no continuous numeric target is provided per-image, except Dataset 1's burned-in spot-temperature text, which is not a machine-readable structured field without OCR/extraction). |
| G. Temperature estimation | **Conditionally possible for Dataset 1 only**, and only after actually extracting the embedded FLIR radiometric data (not done in this audit) or OCR'ing the burned-in spot value (a much weaker, single-point signal, and not necessarily the fault-region temperature per §3's caveat). **Not supported** for Dataset 2 (no calibration retained in the BMP export). |
| H. Health-score regression | **Not supported** by either dataset as-is — no dataset provides a continuous health-score target; one would have to be manually constructed (e.g. from Dataset 2's severity %), which is a design decision, not something already present. |

---

## 12. What these datasets CANNOT legitimately support

- A validated "healthy → moderate → critical" severity scale for Dataset 1 (no such labels exist).
- Bounding-box or fault-*location* detection/segmentation in either dataset (Dataset 2's masks delineate the whole motor, not a fault region).
- Confirmed per-pixel °C values for Dataset 2 at all, or for Dataset 1 without an actual extraction step that was not performed here.
- A claim that Dataset 1's `C` class means one single specific fault type — this is not documented locally and must not be asserted without finding Dataset 1's source paper/documentation.
- Training a generalizable classifier from Dataset 1 using a random per-image split, given the confirmed session-blocked sequence numbering (§8) — this would silently overstate accuracy via leakage.
- Any claim that these datasets represent IDEA LAB's own live deployment scenario — they are lab-bench captures of one motor per dataset under controlled/induced fault conditions, not field data from arbitrary customer machines.

---

## 13. IDEA LAB deployment relevance

The eventual pipeline needs frame-by-frame inference on a live/streaming thermal feed. Both datasets are single static images per capture, not video — this matches IDEA LAB's actual frame-by-frame consumption model reasonably well (a trained classifier could run per-frame exactly as the existing `ThermalAnalyzer` runs per-frame). However: Dataset 1's images contain a burned-in camera overlay (crosshair, temperature text, logo) that a live IDEA LAB camera feed will **not** have — any model trained directly on these images risks keying on the overlay rather than the thermal scene, and would need that overlay region cropped/masked out during training, or fine-tuning/validation on overlay-free frames before deployment.

## 14. Integration compatibility with the existing thermal analyzer

The existing `ThermalAnalyzer`/`extract_thermal_features` (mean/max/min/std intensity, hotspot area/centroid, gradient) operates on relative brightness and would run unchanged on either dataset's images (they're just images). Additional features these datasets could *eventually* support, contingent on the unresolved items above:

- Absolute-temperature statistics (mean/max °C) — **only** if Dataset 1's embedded radiometric data is successfully extracted; not currently possible from Dataset 2.
- Fault-region temperature / temperature rise vs. baseline — would additionally require a fault-location annotation that **neither dataset provides**.
- A learned classification/anomaly *evidence* feature (e.g. "model says X% probability of stator fault") — supportable today via image classification (§11.A) once the class-semantics/leakage issues are resolved, entirely independent of temperature extraction.

No changes to the analyzer were made in this audit.

---

## Summary of what is fact vs. interpretation

Every table above marks its own confidence level, but as a summary: **Dataset 2's labels, counts, and equipment specs are directly documented and were arithmetic-verified against local files.** **Dataset 1's class semantics (H/C/F/M/N meaning) are not locally documented and are inference only** — everything else about Dataset 1 (image properties, FLIR/FFF markers, burned-in temperature readouts, sequence-number leakage risk) was directly observed from the files themselves.

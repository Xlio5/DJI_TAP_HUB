# HC32F460 UART Pin Annotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce an annotated PCB screenshot showing every HC32F460JEUA QFN48 pad that can be configured as USART TX/RX.

**Architecture:** Preserve the supplied screenshot as the base image and add a deterministic annotation layer around N30780. Use blue labels for Func_Grp1 and green labels for Func_Grp2, then verify the output against the 33-pin source list.

**Tech Stack:** Built-in image editing, PNG inspection, HC32F460 Rev1.41 datasheet mapping.

---

### Task 1: Generate the annotation image

**Files:**
- Read: `C:/Users/xlong/AppData/Local/Temp/codex-clipboard-ca065966-8fc2-4d6b-b4b1-ef0f53ce01ed.png`
- Create: `output/imagegen/hc32f460jeua-uart-pin-map.png`

- [ ] **Step 1: Preserve the screenshot and annotate Func_Grp1 pads**

Add blue labels for pins 10-20, 29-34, and 37-38 with their GPIO names.

- [ ] **Step 2: Annotate Func_Grp2 pads**

Add green labels for pins 1, 2, 21, 25-28, 39-43, 45, and 46 with their GPIO names.

- [ ] **Step 3: Add the legend**

Add `Blue: USART1/2` and `Green: USART3/4` without obscuring N30780 pads.

### Task 2: Verify the image

**Files:**
- Test: `output/imagegen/hc32f460jeua-uart-pin-map.png`

- [ ] **Step 1: Verify image readability**

Open the PNG at original resolution and confirm labels are legible and do not cover pad numbers.

- [ ] **Step 2: Verify mapping completeness**

Confirm 19 blue labels and 14 green labels, with no UART label on Pin 44, power, ground, oscillator, reset, or VCAP pins.

- [ ] **Step 3: Read back file metadata**

Confirm the final PNG exists, has non-zero size, and retains the original 1559 x 1007 canvas.

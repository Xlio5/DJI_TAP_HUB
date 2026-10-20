# Open Source Repository Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a clean, buildable GPL-3.0-only monorepo that can be published after adding a Git remote.

**Architecture:** Build a new repository from a strict source whitelist instead of rewriting the private repository history. Keep Android, Linux, protocol, documentation, and safe build utilities together; rename the public `ubuntu/` tree to `linux/` and describe the system with GitHub-native Mermaid diagrams.

**Tech Stack:** Kotlin, Jetpack Compose, Android Gradle Plugin, C++17, CMake, shell, PowerShell, Python 3, Mermaid, Git.

---

### Task 1: Establish the clean repository boundary

**Files:**
- Create: `C:/my_project/tun-nat-hub-open-source/.gitignore`
- Create: `C:/my_project/tun-nat-hub-open-source/scripts/check-public-tree.py`

- [ ] **Step 1: Verify the destination is absent or empty**

Run: `Test-Path C:\my_project\tun-nat-hub-open-source`

Expected: `False`, or an existing empty directory that can be reused without deleting content.

- [ ] **Step 2: Create the public directory skeleton**

Create `android/`, `linux/`, `protocol/`, `docs/`, `scripts/`, and `assets/` beneath the destination.

- [ ] **Step 3: Add deny rules and a deterministic public-tree scanner**

The scanner must reject build outputs, firmware images, APK files, private agent instructions, private keys, common password assignments, known private addresses, and absolute developer-machine paths while allowing source fixtures explicitly reviewed by the maintainer.

- [ ] **Step 4: Run the scanner before migration**

Run: `python scripts/check-public-tree.py .`

Expected: exit code `0` and `Public tree check passed`.

### Task 2: Migrate Android sources by whitelist

**Files:**
- Copy: `android/gradle/`
- Copy: `android/app/src/`
- Copy: `android/app/build.gradle.kts`
- Copy: `android/build.gradle.kts`
- Copy: `android/settings.gradle.kts`
- Copy: `android/gradle.properties`
- Copy: `android/gradlew`
- Copy: `android/gradlew.bat`

- [ ] **Step 1: Inspect Android native dependency declarations**

Run: `Get-Content android/app/src/main/cpp/CMakeLists.txt`

Expected: every local static library referenced by CMake is identified before copying.

- [ ] **Step 2: Copy only build inputs from committed HEAD**

Use `git archive HEAD` or `git show HEAD:<path>` so dirty Gradle caches and local files cannot enter the public tree.

- [ ] **Step 3: Remove machine-specific Android inputs**

Verify `.gradle/`, `local.properties`, `build/`, `dexout/`, `out/`, APK files, signing stores, and captures are absent.

- [ ] **Step 4: Verify the Android project configuration**

Run: `cd android; .\gradlew.bat tasks --all`

Expected: Gradle configures successfully and lists `assembleDebug`.

### Task 3: Migrate Linux and protocol sources by whitelist

**Files:**
- Copy: `ubuntu/CMakeLists.txt` to `linux/CMakeLists.txt`
- Copy: `ubuntu/cmake/` to `linux/cmake/`
- Copy: `ubuntu/src/` to `linux/src/`
- Copy: `ubuntu/tests/` to `linux/tests/`
- Copy: selected production service scripts from `ubuntu/` to `linux/`
- Copy: `protocol/` to `protocol/`

- [ ] **Step 1: Inventory canonical build and runtime inputs**

Run: `git ls-tree -r --name-only HEAD ubuntu protocol`

Expected: source, tests, and production scripts are separated from backups, captures, and generated builds.

- [ ] **Step 2: Copy committed source files and tests**

Exclude `.bak`, `Testing/`, every `build*/` directory, binaries, packet captures, logs, and one-off deployment scripts containing device credentials.

- [ ] **Step 3: Update public paths from `ubuntu/` to `linux/`**

Search: `rg -n "ubuntu/|../ubuntu|C:\\\\|/home/" linux protocol`

Expected: no stale repository path or developer-machine path remains.

- [ ] **Step 4: Configure and build the host-testable Linux targets**

Run: `cmake -S linux -B build/linux -DCMAKE_BUILD_TYPE=Release; cmake --build build/linux --parallel`

Expected: configuration and compilation complete successfully, or hardware-only targets are clearly gated and documented.

### Task 4: Add safe contributor utilities

**Files:**
- Create: `scripts/build-android.ps1`
- Create: `scripts/build-linux.sh`
- Create: `scripts/check-public-tree.py`

- [ ] **Step 1: Add an Android build wrapper**

The wrapper resolves the repository root and invokes `android/gradlew.bat assembleDebug` without credentials or machine-specific paths.

- [ ] **Step 2: Add a Linux build wrapper**

The wrapper configures `build/linux` and builds with CMake using only repository-relative paths.

- [ ] **Step 3: Exercise both wrappers**

Run: `powershell -ExecutionPolicy Bypass -File scripts/build-android.ps1`

Run: `wsl bash scripts/build-linux.sh`

Expected: both wrappers return zero when their documented prerequisites are installed.

### Task 5: Write the public documentation set

**Files:**
- Create: `README.md`
- Create: `README.zh-CN.md`
- Create: `docs/architecture.md`
- Create: `docs/getting-started.md`
- Create: `docs/protocol.md`
- Create: `docs/troubleshooting.md`

- [ ] **Step 1: Write English and Chinese entry points**

Both READMEs must describe the real Android + V3s/Linux system, supported RC paths, repository layout, prerequisites, quick build commands, security posture, license, and links to the detailed documents.

- [ ] **Step 2: Add five Mermaid diagrams**

`docs/architecture.md` must include system overview, IP packet flow, RC input flow, startup sequence, and module relationship diagrams that render on GitHub without external assets.

- [ ] **Step 3: Document setup without private environment values**

Use documentation-only ranges such as `192.0.2.0/24` and placeholders such as `<device-ip>`; do not include passwords, adb keys, SSH keys, or copied device identifiers.

- [ ] **Step 4: Validate links and Mermaid fences**

Run a repository-relative Markdown link checker and verify every Mermaid fence has a matching close fence and one of the five required headings.

### Task 6: Add project governance and licensing

**Files:**
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`

- [ ] **Step 1: Install the canonical GPL-3.0-only license text**

Fetch the plain-text license from `https://www.gnu.org/licenses/gpl-3.0.txt`, then read it back and confirm the title and version line.

- [ ] **Step 2: Add contributor guidance**

Describe issue quality, focused commits, Android/Linux build expectations, test expectations, DCO-free contribution flow, and the requirement that contributed code remains GPL-3.0-only compatible.

- [ ] **Step 3: Add private vulnerability reporting guidance**

Avoid inventing an email address; direct reporters to GitHub private vulnerability reporting when enabled and otherwise to a private maintainer contact channel listed by the repository owner.

### Task 7: Audit, build, initialize, and commit

**Files:**
- Verify: entire `C:/my_project/tun-nat-hub-open-source/` tree

- [ ] **Step 1: Run forbidden-content scans**

Run: `python scripts/check-public-tree.py .`

Run targeted searches for credentials, private keys, absolute paths, binary releases, build directories, and excluded private project metadata.

Expected: no findings.

- [ ] **Step 2: Run source and documentation verification**

Build Android, configure/build Linux, run available tests, check Markdown links, inspect Mermaid blocks, and list the largest files to confirm GitHub compatibility.

- [ ] **Step 3: Initialize a fresh Git history**

Run: `git init -b main; git add .; git commit -m "feat: publish initial GPL-3.0 source release"`

Expected: exactly one clean initial commit, no remote, and `git status --short` returns no output.

- [ ] **Step 4: Read back the publication state**

Run: `git status --short; git log -1 --oneline; git remote -v; git ls-files`

Expected: clean status, one initial commit, no remote, and only approved public files.

- [ ] **Step 5: Record the reusable publishing decision**

Create the required Obsidian backflow note describing why a clean whitelist mirror was used instead of history rewriting and how the scanner prevents accidental disclosure.

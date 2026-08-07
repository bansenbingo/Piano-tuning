# Project Memory

This file is the project memory and OpenCode guidance for `Piano-tuning`. Read it before making project changes. Commit numbering and branch policy are maintained in `ProjectRules/COMMIT_CONVENTIONS.md`.

## Project Goal

- `Piano-tuning` is Teddy's undergraduate graduation thesis project.
- The `Sandbox/Microphone/MicrophoneA7` Nexys A7-100T design records board PDM-microphone audio when `SW[0]` is asserted and plays a completed recording when `SW[15]` is asserted.

## Development Process

- Do not use terminal-based Vivado synthesis, implementation, simulation, or hardware experiments for this project. Vivado-related changes must be validated by the user programming the board and reporting the observed results.
- All OpenCode commits on current and future branches must follow `ProjectRules/COMMIT_CONVENTIONS.md`, which is the user-editable source of the commit policy.
- New branches inherit the version prefix of their source branch; new long-lived branches must be added to `ProjectRules/COMMIT_CONVENTIONS.md`.
- Current latest topics are `main=0.6` and `sandbox-audio-upload=1.6`.
- Enable the repository hook with `git config core.hooksPath .githooks` after cloning.

## Current Status

- Microphone RTL uses a 2.5 MHz PDM clock, 128-bit moving-average decimation, a 65,536-byte on-chip recording buffer (about 3.36 s), and open-drain PWM audio output required by Nexys A7.

## Working Notes

- Update this file when the user provides durable project context, goals, decisions, or process notes.
- Do not treat temporary debugging details as project memory unless the user explicitly wants them retained.

# Project Memory

This file is the persistent project memory for OpenCode agents working in this repository. Keep it concise, factual, and current as the project evolves.

## Project Goal

- TBD: Record the overall development goal for this project.
- Current known context: `Piano-tuning` is Teddy's undergraduate graduation thesis project.
- The `Sandbox/Microphone/MicrophoneA7` Nexys A7-100T design records board PDM-microphone audio when `SW[0]` is asserted and plays a completed recording when `SW[15]` is asserted.

## Development Process

- TBD: Record milestones, major implementation steps, and important decisions as they happen.
- Do not use terminal-based Vivado synthesis, implementation, simulation, or hardware experiments for this project. Vivado-related changes must be validated by the user programming the board and reporting the observed results.

## Design And Thinking

- TBD: Record architecture notes, reasoning, constraints, tradeoffs, and discarded approaches.

## Current Status

- TBD: Record what is working, what is incomplete, and the next intended work.
- Microphone RTL uses a 2.5 MHz PDM clock, 128-bit moving-average decimation, a 65,536-byte on-chip recording buffer (about 3.36 s), and open-drain PWM audio output required by Nexys A7.

## Working Notes For Agents

- Read this file before making project changes.
- Update this file when the user provides durable project context, goals, decisions, or process notes.
- Do not treat temporary debugging details as project memory unless the user explicitly wants them retained.

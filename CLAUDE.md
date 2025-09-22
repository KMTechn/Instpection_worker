# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Korean Quality Inspection System (품질 검사 시스템) - a desktop application for manufacturing line quality control. The application allows workers to scan barcodes to track good/defective products in real-time, with foot pedal integration for defective item classification.

## Core Architecture

### Main Components

- **Single-file application**: `Inspection_worker.py` (~5000 lines) contains the entire application
- **Three main classes**:
  - `InspectionSession`: Manages individual work sessions and barcode scanning
  - `RemnantCreationSession`: Handles creation of remnant/leftover product labels
  - `InspectionProgram`: Main application class with GUI and state management

### Key Features

- Barcode scanning with USB scanners for product identification
- F12 foot pedal integration for defective product marking
- Real-time progress tracking and statistics
- Master label (현품표) QR code scanning to start work sessions
- Rework mode for previously defective products
- Auto-save and recovery of work sessions
- Automatic updates from GitHub releases

## Development Environment

### Dependencies

Install required packages:
```bash
pip install -r requirements.txt
```

Required packages:
- `requests` - HTTP requests for updates
- `pygame` - Audio playback for scan feedback
- `keyboard` - Global hotkey detection (F12 foot pedal)
- `Pillow` - Image processing for labels
- `qrcode` - QR code generation

### File Structure

```
C:\KMTECH Program\Instpection_worker\
├── Inspection_worker.py          # Main application
├── requirements.txt               # Python dependencies
├── assets/                        # Required assets
│   ├── Item.csv                  # Product database
│   ├── *.wav                     # Audio files for feedback
│   ├── *.png                     # Product tray images
│   └── logo.ico                  # Application icon
├── config/                       # Configuration files
│   └── inspection_settings.json  # UI settings (scale, positions)
└── updater.bat                   # Auto-update script
```

### Critical Dependencies

- **C:\Sync folder**: MUST exist - all log files are saved here
- **assets/Item.csv**: Product database mapping item codes to specifications
- **Audio files**: success.wav, error.wav, combo.wav for user feedback
- **Product images**: KMC_LHD.png, KMC_RHD.png, HMC_LHD_RHD.png for tray visualization

## Common Development Tasks

### Running the Application

```bash
python Inspection_worker.py
```

### Testing

The application includes an automated testing sequence that simulates barcode scanning:
- Located in `InspectionProgram.start_automated_test()` method
- Simulates worker login, master label scanning, product scanning, and various edge cases
- Tests both standard inspection and rework modes

### Configuration

Settings are stored in `config/inspection_settings.json`:
- `scale_factor`: UI scaling (adjustable with Ctrl+mouse wheel)
- `column_widths_*`: Table column widths for different views
- `paned_window_sash_positions`: Layout panel positions
- `scan_delay`: Delay between barcode scans in seconds

### Audio System

Uses pygame for audio feedback:
- Initialize with `pygame.mixer.init()`
- Audio files must be in assets/ directory
- Critical for user experience during scanning operations

## Important Implementation Details

### Barcode Scanning Flow

1. Worker logs in with their name
2. Scan master label (현품표) QR code to start session
3. Scan individual product barcodes:
   - Normal scan = good product
   - F12 + scan = defective product
4. Auto-submit when target quantity reached

### Data Logging

All events logged to `C:\Sync\검사작업이벤트로그_[worker]_[date].csv`:
- Session start/end events
- Individual product scans with timestamps
- Quality judgments (good/defective)
- System events (errors, mode changes)

### State Management

- Current session state stored in memory and auto-saved
- Recovery mechanism for unexpected shutdowns
- Modal dialogs for error handling and user feedback

### Update System

- Checks GitHub releases on startup
- Downloads and applies updates automatically
- Version tracking: `CURRENT_VERSION = "v2.0.7"`
- Update URL: `https://github.com/KMTechn/Instpection_worker`

## Debugging and Troubleshooting

### Common Issues

- **Missing C:\Sync folder**: Application will fail to start
- **Missing assets/Item.csv**: Cannot load product database
- **Audio initialization errors**: Check pygame mixer initialization
- **Barcode scanner not working**: Test in notepad first, ensure USB connection

### Log Analysis

Event logs in C:\Sync contain detailed timestamps and event types for debugging work session issues.

### UI Scaling Issues

If UI elements are too small/large, check `scale_factor` in inspection_settings.json or use Ctrl+mouse wheel during runtime.
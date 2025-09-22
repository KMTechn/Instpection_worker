# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Korean Quality Inspection System (품질 검사 시스템) - a desktop application for manufacturing line quality control. The application allows workers to scan barcodes to track good/defective products in real-time, with foot pedal integration for defective item classification.

## Core Architecture

### Main Components

- **Single-file application**: `Inspection_worker.py` (~5000 lines) contains the entire application
- **Data models** in `core/models.py`:
  - `InspectionSession`: Standard quality inspection sessions
  - `RemnantCreationSession`: Handles creation of remnant/leftover product labels
  - `DefectiveMergeSession`: Manages bulk defective product consolidation (default target: 48 units)
- **Mode-based UI system**: Standard inspection, rework, remnant creation, and defective merge modes
- **Test system**: Comprehensive test codes for simulation and validation

### Key Features

- Barcode scanning with USB scanners for product identification
- F12 foot pedal integration for defective product marking
- Real-time progress tracking and statistics
- Master label (현품표) QR code scanning to start work sessions
- Rework mode for previously defective products
- Defective merge mode for bulk defective product handling
- Auto-save and recovery of work sessions
- Automatic updates from GitHub releases
- Comprehensive test code system with special barcode commands

### Multi-Mode Operation

- **Standard Mode**: Normal quality inspection workflow
- **Rework Mode**: Processing previously defective items after repair
- **Remnant Mode**: Creating labels for leftover/remnant products
- **Defective Merge Mode**: Consolidating multiple defective items (target quantity: 48)

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
├── Inspection_worker.py          # Main application (~5000 lines)
├── core/
│   └── models.py                 # Data models using dataclasses
├── tests/                        # Unit test suite (44 tests)
│   ├── run_tests.py             # Test runner
│   ├── test_models.py           # Data model tests
│   ├── test_defect_mode.py      # Defect mode functionality tests
│   ├── test_config.py           # Configuration tests
│   ├── test_file_handler.py     # File handling tests
│   └── test_integration.py      # Integration tests
├── TEST_CODE.txt                # Complete test code documentation
├── requirements.txt             # Python dependencies
├── assets/                      # Required assets
│   ├── Item.csv                # Product database
│   ├── *.wav                   # Audio files for feedback
│   ├── *.png                   # Product tray images
│   └── logo.ico                # Application icon
├── config/                     # Configuration files
│   └── inspection_settings.json # UI settings (scale, positions)
└── updater.bat                 # Auto-update script
```

### Critical Dependencies

- **C:\Sync folder**: MUST exist - all production log files are saved here
- **C:\Sync\TEST folder**: Auto-created for test-related logs (separate from production)
- **assets/Item.csv**: Product database mapping item codes to specifications
- **Audio files**: success.wav, error.wav, combo.wav for user feedback
- **Product images**: KMC_LHD.png, KMC_RHD.png, HMC_LHD_RHD.png for tray visualization

## Common Development Tasks

### Running the Application

```bash
python Inspection_worker.py
```

### Running Tests

Complete test suite with 44 tests across 5 modules:
```bash
# Run all tests
python tests/run_tests.py

# Run specific test modules
python tests/run_tests.py config
python tests/run_tests.py models
python tests/run_tests.py defect_mode
python tests/run_tests.py integration
```

### Test Code System

The application includes special barcode commands for testing (all test codes only work in standard inspection mode):

**Automated Testing:**
- `_RUN_AUTO_TEST_`: Comprehensive system simulation
- `_TEST_DEFECT_MODE_`: Defect mode specific testing
- `_TEST_DEFECT_MERGE_`: Defective merge functionality testing

**Unit Tests:**
- `_RUN_UNIT_TESTS_`: Execute all 44 unit tests
- `_RUN_TESTS_[module]_`: Run specific test modules

**Data Generation:**
- `TEST_LOG_[quantity]`: Generate mixed test logs
- `TEST_LOG_[quantity]_GOOD`: Generate good-only test logs
- `_CREATE_DEFECTS_[item]_[qty]_`: Create test defect data

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

### Data Logging System

**Production Logs** (C:\Sync):
- `검사작업이벤트로그_[worker]_[date].csv`: Standard inspection logs
- `리워크작업이벤트로그_[worker]_[date].csv`: Rework mode logs

**Test Logs** (C:\Sync\TEST):
- `TEST_검사작업이벤트로그_[worker]_[date].csv`: Test inspection logs
- `TEST_리워크작업이벤트로그_[worker]_[date].csv`: Test rework logs

The system automatically detects test-related events and routes them to separate TEST folder files.

### Mode System Architecture

**UI Mode Management** (`_apply_mode_ui` function):
- Controls button visibility per mode
- Prevents UI overlap between modes
- Mode-specific color schemes

**Mode Validation**:
- Test codes restricted to standard inspection mode only
- Mode-specific functionality isolation
- Safe mode transitions

### State Management

- Current session state stored in memory and auto-saved
- Recovery mechanism for unexpected shutdowns
- Modal dialogs for error handling and user feedback
- Multi-session support for different modes

### Defective Merge Mode

- Default target quantity: 48 defective items
- Bulk processing of defective products
- Automatic defect label generation upon completion
- Integration with main defect tracking system

### Update System

- Checks GitHub releases on startup
- Downloads and applies updates automatically
- Version tracking in `CURRENT_VERSION` constant
- Update URL: `https://github.com/KMTechn/Instpection_worker`

## Debugging and Troubleshooting

### Common Issues

- **Missing C:\Sync folder**: Application will fail to start
- **Missing assets/Item.csv**: Cannot load product database
- **Audio initialization errors**: Check pygame mixer initialization
- **Barcode scanner not working**: Test in notepad first, ensure USB connection
- **Test codes not working**: Ensure you're in standard inspection mode

### Log Analysis

Event logs in C:\Sync contain detailed timestamps and event types for debugging work session issues. Test logs are automatically separated into the TEST subfolder.

### UI Scaling Issues

If UI elements are too small/large, check `scale_factor` in inspection_settings.json or use Ctrl+mouse wheel during runtime.

### Mode-Specific Debugging

- Use `_TEST_UI_RESPONSIVE_` to test UI scaling and layout
- Use `_SECURITY_VALIDATION_TEST_` for input validation testing
- Use `_GENERATE_TEST_REPORT_` for comprehensive system health reports
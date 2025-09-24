# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Korean Quality Inspection System (품질 검사 시스템) - a desktop application for manufacturing line quality control. The application allows workers to scan barcodes to track good/defective products in real-time, with foot pedal integration for defective item classification.

## Core Architecture

The application follows a modular architecture with a single-file main application and separate utility modules:

### Main Application Structure

- **`Inspection_worker.py`**: Monolithic main application (~5000 lines) containing:
  - `InspectionWorkerGUI` class: Core UI and business logic
  - `ConfigManager` class: Application configuration management
  - Event handlers for barcode scanning, UI interactions, and mode switching
  - Integration with hardware (barcode scanners, F12 foot pedal via `keyboard` library)
  - Auto-update mechanism using GitHub releases API

### Core Data Models (`core/models.py`)

- **`InspectionSession`**: Standard quality inspection workflow data
  - Tracks good/defective items, barcode scanning history, timing metrics
  - Support for test sessions, partial submissions, and session recovery
- **`RemnantCreationSession`**: Leftover product label creation
- **`DefectiveMergeSession`**: Bulk defective product consolidation (target: 48 units)

### UI Architecture (`ui/` modules)

- **Component-based UI system** using abstract `BaseUIComponent` class
- **`ScannerInputComponent`**: Specialized barcode scanner input handling
- **`ProgressDisplayComponent`**: Real-time progress visualization
- **`DataDisplayComponent`**: Tabular data presentation
- **Mode-based UI switching**: Standard inspection, rework, remnant creation, defective merge

### Utility Modules (`utils/` directory)

- **`file_handler.py`**: File operations, PyInstaller resource handling
- **`logger.py`**: Event logging system with CSV output
- **`exceptions.py`**: Custom exception hierarchy for error handling

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
C:\KMTECH Program\Inspection_worker\
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

### Critical Runtime Dependencies

**Required System Directories:**
- **`C:\Sync`**: MUST exist - application fails to start without this directory
  - Production event logs: `검사작업이벤트로그_[worker]_[date].csv`
  - Rework logs: `리워크작업이벤트로그_[worker]_[date].csv`
- **`C:\Sync\labels\[YYYYMMDD]`**: Auto-created daily for label generation
  - Master labels (현품표): `현품표_[WID]_[timestamp].png`
  - Defective labels (불량표): `불량표_[DEFECT-ID]_[timestamp].png`
  - Remnant labels (잔량표): `잔량표_[SPARE-ID]_[timestamp].png`

**Required Asset Files:**
- **`assets/Item.csv`**: Product database (item codes → specifications mapping)
- **Audio feedback**: `success.wav`, `error.wav`, `combo.wav`
- **Product visualization**: `KMC_LHD.png`, `KMC_RHD.png`, `HMC_LHD_RHD.png`
- **Application icon**: `logo.ico`

**Configuration Files:**
- **`config/inspection_settings.json`**: UI scaling, column widths, scan delays
- **`config.json`**: Main application configuration (created if missing)

## Development Commands

### Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Verify critical directories exist
mkdir -p "C:\Sync"
```

### Running the Application

```bash
# Run main application
python Inspection_worker.py

# Run with debug output (if implemented)
python Inspection_worker.py --debug
```

### Testing

**Unit Tests** (44 tests across 5 modules):
```bash
# Run all tests
python tests/run_tests.py

# Run specific test modules
python tests/run_tests.py config      # Configuration tests
python tests/run_tests.py models      # Data model tests
python tests/run_tests.py file_handler # File handling tests
python tests/run_tests.py defect_mode  # Defect mode functionality
python tests/run_tests.py integration  # Integration & system health tests

# Run single test file directly
python -m unittest tests.test_models.TestInspectionSession
```

**In-Application Testing** (via special barcodes):
```bash
# Available test codes (scan or type in application):
_RUN_UNIT_TESTS_           # Execute all 44 unit tests
_RUN_TESTS_[module]_       # Run specific test modules
_RUN_AUTO_TEST_            # Full system simulation
_TEST_DEFECT_MODE_         # Complete defective workflow test
_GENERATE_TEST_REPORT_     # System health report
```

### Code Analysis

```bash
# Check Python syntax
python -m py_compile Inspection_worker.py

# Find TODO/FIXME comments
grep -r "TODO\|FIXME" . --include="*.py"

# Count lines of code
find . -name "*.py" -exec wc -l {} + | tail -1
```

### Test Code System

The application includes special barcode commands for testing (all test codes only work in standard inspection mode):

**Automated Testing:**
- `_RUN_AUTO_TEST_`: Comprehensive system simulation
- `_TEST_DEFECT_MODE_`: Complete defective workflow testing (2 master label sessions + defect merge + mixed barcode scanning)
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

### Application Lifecycle

1. **Startup Sequence**:
   - Load configuration from `config/inspection_settings.json`
   - Initialize pygame audio system
   - Check for C:\Sync directory existence (critical)
   - Load product database from `assets/Item.csv`
   - Check for updates via GitHub API
   - Setup global F12 keyboard hook for defective scanning

2. **Session Management**:
   - Auto-save current session state to prevent data loss
   - Recovery mechanism for unexpected shutdowns
   - Multi-mode state isolation (standard/rework/remnant/defective merge)

3. **Hardware Integration**:
   - USB barcode scanner input via tkinter Entry widgets
   - F12 foot pedal detection using `keyboard` library global hooks
   - Audio feedback through pygame mixer

### Data Flow Architecture

**Barcode Processing Pipeline**:
```
Raw Barcode Input → Input Validation → Mode-specific Processing →
Session State Update → UI Refresh → Event Logging → Audio Feedback
```

**Key Functions in `Inspection_worker.py`**:
- `_on_scan()`: Main barcode processing entry point
- `_apply_mode_ui()`: Mode-specific UI state management
- `_process_*_scan()`: Mode-specific barcode handling methods
- `_update_*_display()`: UI data synchronization methods

### Barcode Scanning Flow

#### Standard Inspection Mode:
1. Worker logs in with their name
2. Scan master label (현품표) QR code to start session
3. Scan individual product barcodes:
   - Normal scan = good product
   - F12 + scan = defective product
4. Auto-submit when target quantity reached

#### Defective Merge Mode:
1. Switch to defective merge mode
2. Select item from available defects list (left panel) OR scan any defective product barcode to auto-start session
3. Scan defective product barcodes (individual product barcodes, NOT defective label QR codes):
   - From previous inspection sessions (available_defects)
   - New defective products without master labels (auto-recorded as INSPECTION_DEFECTIVE events)
4. Generate defective labels:
   - **Manual**: Click "불량표 생성" button anytime (for temporary storage when switching items)
   - **Automatic**: When target quantity (48 items) is reached (for external warehouse shipment)

**Important Notes:**
- Current system processes individual defective product barcodes only
- Defective label QR code scanning for merging multiple defective labels is NOT implemented
- No overflow handling when scanned quantity exceeds target quantity
- Each defective label contains QR code: `{'id': 'DEFECT-YYYYMMDD-HHMMSS...', 'code': 'item_code', 'qty': quantity}`

### Data Logging System

**Production Logs** (C:\Sync):
- `검사작업이벤트로그_[worker]_[date].csv`: Standard inspection logs
- `리워크작업이벤트로그_[worker]_[date].csv`: Rework mode logs

**Label Generation Files** (C:\Sync\labels\[YYYYMMDD]):
- `현품표_[WID]_[timestamp].png`: Master labels generated during inspection
- `불량표_[DEFECT-ID]_[timestamp].png`: Defective labels (manual or auto-generated)
- `잔량표_[SPARE-ID]_[timestamp].png`: Remnant labels for leftover products

**Important Note**: Test events are now processed in the same way as production events for proper validation. All logs go to the main C:\Sync folder.

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
- Processes **individual defective product barcodes** (NOT defective label QR codes)
- Bulk processing of defective products from multiple inspection sessions
- Two types of defective label generation:
  - **Manual Generation**: Worker clicks "불량표 생성" button when switching to different items (임시 보관용)
  - **Automatic Generation**: System auto-generates when target quantity (48 items) is reached (외부 창고 출고용)
- Supports direct scanning of defective product barcodes without master labels
- Integration with main defect tracking system

**Limitations:**
- No support for scanning existing defective labels to merge multiple defective batches
- No overflow handling when combining defective batches exceeds target quantity
- Manual splitting required if defective quantity combinations don't match target

### Error Handling & Exception Architecture

**Custom Exception Hierarchy** (`utils/exceptions.py`):
```
InspectionError (base)
├── ConfigurationError    # Settings/config issues
├── FileHandlingError     # File I/O problems
├── BarcodeError         # Barcode validation failures
├── SessionError         # Session state issues
├── ValidationError      # Data validation failures
├── NetworkError         # Update/network issues
└── UpdateError          # Auto-update failures
```

**Error Display Strategy**:
- Modal dialogs for user-facing errors with Korean messages
- Full-screen error displays for critical scanning errors
- Console logging for development debugging
- Event logging for production error tracking

### Update System

- Checks GitHub releases on startup via API
- Downloads and applies updates automatically using `updater.bat`
- Version tracking in `CURRENT_VERSION` constant
- Update repository: `https://github.com/KMTechn/Inspection_worker`
- Graceful fallback if update check fails

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
# EDS Tool - Automatic Workflow CLI

## Overview

The EDS Tool now supports a command-line interface for automated batch processing of EDS spectra without launching the GUI. This is ideal for scripting, batch processing, and automated analysis pipelines.

## Usage

### Basic Auto Workflow

```cmd
python eds_tool.py --auto --elements Fe,O,Cu path/to/spectra/*.eds
```

Or with a directory:

```cmd
python eds_tool.py --auto --elements Fe,O,Cu path/to/spectra/
```

### With Maximum Energy Limit for Plots

```cmd
python eds_tool.py --auto --elements Fe,O,Cu --max-energy 10 path/to/spectra/*.eds
```

This limits the X-axis range of exported plots to 0-10 keV.

## What the Auto Workflow Does

The automatic workflow performs the following steps:

1. **Load Spectra**: Loads all specified EDS files (or recursively searches directories)
2. **Set Elements**: Applies the element list from `--elements` to all spectra
3. **Compute Intensities**: Calculates peak intensities using **summing method** (not fitting)
4. **Export Spectra**: Saves each spectrum in multiple formats:
   - EMSA format (`.emsa`)
   - CSV format (`.csv`)
   - Files saved in same folder as original `.eds` file
5. **Export Plots**: Generates plots for each spectrum in multiple formats:
   - PNG (`.png`)
   - BMP (`.bmp`)
   - SVG (`.svg`)
   - Files saved in same folder as original `.eds` file
6. **Export Intensity Table**: Creates a summary CSV table with all computed intensities
   - Saved in the longest common folder of all input files
   - Filename: `summed_intensities.csv`
   - Format: Rows = spectra, Columns = element lines

## Command-Line Arguments

### Required Arguments

- **spectra**: One or more `.eds` files or directories containing `.eds` files
  - Can be individual files: `file1.eds file2.eds`
  - Can be directories (searched recursively): `folder1/ folder2/`
  - Can be glob patterns (in shells that support it): `data/**/*.eds`

### Optional Arguments

- `--elements ELEMENTS`: Comma-separated element symbols
  - Example: `--elements Fe,O,Cu,Ni`
  - Required if you want intensity calculations and element line markers on plots
  
- `--auto`: Enable automatic workflow mode (no GUI)
  - Without this flag, the GUI will launch normally
  
- `--max-energy FLOAT`: Maximum energy in keV for plot X-axis
  - Example: `--max-energy 10` limits plots to 0-10 keV range
  - Default: Uses full spectrum range
  - Only affects plot exports, not data exports

- `--cps`: Use counts per second as unit instead of counts
  - Recommended for comparison of spectra

## Customizing Export Formats

You can modify the export formats by editing the configuration at the top of `eds_tool.py`:

```python
# Configuration for auto workflow exports
AUTO_SPECTRUM_FORMATS = ['emsa', 'csv']  # Formats for spectrum export
AUTO_PLOT_FORMATS = ['png', 'bmp', 'svg']  # Formats for plot export
```

### Available Spectrum Formats

- `'emsa'` - EMSA/MAS format (standard for EDS)
- `'csv'` - Comma-separated values
- Other formats supported by HyperSpy (check HyperSpy documentation)

### Available Plot Formats

- `'png'` - Portable Network Graphics (raster)
- `'bmp'` - Bitmap (raster)
- `'svg'` - Scalable Vector Graphics (vector)
- `'pdf'` - Portable Document Format (vector)
- `'jpg'` or `'jpeg'` - JPEG (raster, compressed)
- `'tiff'` or `'tif'` - Tagged Image File Format (raster)
- `'eps'` - Encapsulated PostScript (vector)

## Example Workflows

### Process All Spectra in a Folder

```cmd
python eds_tool.py --auto --elements Fe,O,Si,Al samples/
```

### Process Specific Files with Energy Limit

```cmd
python eds_tool.py --auto --elements Cu,Ni --max-energy 12 sample1.eds sample2.eds sample3.eds
```

### Batch Processing Script (Windows)

Create a batch file `process_all.bat`:

```cmd
@echo off
python eds_tool.py --auto --elements Fe,O,Cu,Ni,Cr --max-energy 15 data\batch1\
python eds_tool.py --auto --elements Fe,O,Cu --max-energy 10 data\batch2\
echo Processing complete!
pause
```

### Bash Script (Linux/Mac)

Create a shell script `process_all.sh`:

```bash
#!/bin/bash
python eds_tool.py --auto --elements Fe,O,Cu,Ni,Cr --max-energy 15 data/batch1/
python eds_tool.py --auto --elements Fe,O,Cu --max-energy 10 data/batch2/
echo "Processing complete!"
```

## Output File Locations

### Spectrum and Plot Files

Each spectrum's exported files are saved **in the same folder as the original `.eds` file**:

```
original_folder/
├── spectrum1.eds          (original)
├── spectrum1.emsa         (exported)
├── spectrum1.csv          (exported)
├── spectrum1.png          (exported plot)
├── spectrum1.bmp          (exported plot)
└── spectrum1.svg          (exported plot)
```

### Intensity Table

The intensity table is saved in the **longest common folder** of all input files:

**Example 1** - All files in same folder:
```
data/
├── spectrum1.eds
├── spectrum2.eds
└── summed_intensities.csv  ← saved here
```

**Example 2** - Files in different subfolders:
```
data/
├── batch1/
│   └── spectrum1.eds
├── batch2/
│   └── spectrum2.eds
└── summed_intensities.csv  ← saved here (common parent)
```

## Differences from GUI Mode

| Feature | GUI Mode | Auto Mode |
|---------|----------|-----------|
| Interactive | Yes | No |
| Element selection | Manual per spectrum | Applied to all from CLI |
| Intensity method | Summing or Fitting | **Summing only** |
| Export formats | User selects | Configured in code |
| Plot display | Interactive matplotlib | Saved to files |
| Progress feedback | Visual | Console output |

## Troubleshooting

### No Intensities Computed

**Symptom**: Output shows "Intensities computed for 0/N spectra"

**Solution**: Make sure you specified `--elements`:
```cmd
python eds_tool.py --auto --elements Fe,O,Cu spectra/
```

### No Common Folder for Intensity Table

**Symptom**: Warning "Could not determine common folder for intensity table"

**Cause**: Input files have no common parent folder (e.g., from different drives)

**Solution**: Provide files from a common directory structure, or the table won't be saved

### Module Not Found Errors

**Symptom**: `ModuleNotFoundError` when running

**Solution**: Make sure you're in the correct conda environment:
```cmd
conda activate eds-tools
python eds_tool.py --auto ...
```

## Integration with Other Tools

The auto workflow is designed to integrate easily with:

- **Batch scripts** for automated processing
- **Python scripts** calling `subprocess` or `os.system()`
- **Make/CMake** build systems for reproducible analysis
- **CI/CD pipelines** for automated testing
- **Job schedulers** for HPC environments

## Future Enhancements

Potential additions (not yet implemented):

- [ ] Add `--fit` option to use fitting instead of summing
- [ ] Add `--output-dir` to specify custom output location
- [ ] Add `--formats` CLI argument to override default formats
- [ ] Add `--parallel` for multi-threaded processing
- [ ] Add JSON output format for machine-readable results
- [ ] Add progress bar for large batches

## See Also

- Main README for GUI usage
- `OPTIMIZATION_NOTES.md` for build optimization details
- `BUILD_README.md` for creating standalone executables

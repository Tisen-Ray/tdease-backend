# Visualization Nodes Specification

## ADDED Requirements

### Requirement 1: Generic Visualization Node Container

**User Story:** As a user, I want to use a generic visualization node container that can host different chart types, so that I can visualize analysis results in the workflow.

#### Acceptance Criteria

1. WHEN a visualization node is created THEN the system SHALL render a container with three regions: input area, visualization area, and output area
2. WHEN data is passed to the visualization node THEN the system SHALL parse the data format (TSV/CSV/JSON) and prepare it for rendering
3. WHEN the visualization type is changed THEN the system SHALL re-render the chart with the same data using the new chart type
4. WHEN the node is in edit mode THEN the system SHALL display configuration panels for chart settings and data mapping
5. WHEN the node is in view mode THEN the system SHALL display only the visualization without edit controls

#### Scenario: Create scatter plot visualization
- **WHEN** user adds a visualization node to the workflow
- **THEN** the system SHALL display an empty visualization container
- **AND** the system SHALL show configuration options for chart type selection

#### Scenario: Load data into visualization
- **WHEN** upstream node provides data to the visualization node
- **THEN** the system SHALL parse the data and automatically detect available columns
- **AND** the system SHALL render the chart with default column mappings

#### Scenario: Switch chart type
- **WHEN** user changes the chart type from scatter to heatmap
- **THEN** the system SHALL re-render the visualization with the new chart type
- **AND** the system SHALL preserve the data and column mappings

### Requirement 2: Scatter Plot Visualization

**User Story:** As a user, I want to visualize high-dimensional data as scatter plots, so that I can identify patterns and clusters in mass spectrometry data.

#### Acceptance Criteria

1. WHEN rendering a scatter plot THEN the system SHALL map data columns to X, Y, and optional Z axes
2. WHEN data points are rendered THEN the system SHALL support color mapping based on a selected column
3. WHEN data points are rendered THEN the system SHALL support size mapping based on a selected column
4. WHEN the user hovers over a point THEN the system SHALL display a tooltip with all data values
5. WHEN the user zooms or pans THEN the system SHALL update the visualization smoothly

#### Scenario: Render scatter plot with color mapping
- **WHEN** user selects X, Y columns and a color column
- **THEN** the system SHALL render points with colors representing the color column values
- **AND** the system SHALL display a color scale legend

#### Scenario: Hover tooltip display
- **WHEN** user hovers over a data point
- **THEN** the system SHALL display a tooltip showing all column values for that point
- **AND** the tooltip SHALL disappear when the mouse leaves the point

### Requirement 3: Heatmap Visualization

**User Story:** As a user, I want to visualize matrix data as heatmaps, so that I can analyze expression patterns and correlations.

#### Acceptance Criteria

1. WHEN rendering a heatmap THEN the system SHALL accept matrix data (rows × columns)
2. WHEN rendering a heatmap THEN the system SHALL support color intensity mapping based on data values
3. WHEN the user hovers over a cell THEN the system SHALL display the row, column, and value
4. WHEN the user zooms THEN the system SHALL maintain readability of cell labels
5. WHEN data contains missing values THEN the system SHALL handle them gracefully (display as gray or skip)

#### Scenario: Render heatmap with intensity mapping
- **WHEN** user provides matrix data and selects intensity column
- **THEN** the system SHALL render a heatmap with color intensity representing values
- **AND** the system SHALL display row and column labels

#### Scenario: Handle missing values
- **WHEN** heatmap data contains null or NaN values
- **THEN** the system SHALL render those cells with a distinct color (e.g., gray)
- **AND** the system SHALL not break the visualization

### Requirement 4: Volcano Plot Visualization

**User Story:** As a user, I want to visualize differential expression results as volcano plots, so that I can identify significant genes or proteins.

#### Acceptance Criteria

1. WHEN rendering a volcano plot THEN the system SHALL map log2 fold-change to X-axis and -log10 p-value to Y-axis
2. WHEN rendering a volcano plot THEN the system SHALL support threshold lines for significance cutoffs
3. WHEN the user hovers over a point THEN the system SHALL display the gene/protein name and statistics
4. WHEN points exceed thresholds THEN the system SHALL color them differently (e.g., red for up-regulated, blue for down-regulated)
5. WHEN the user clicks a point THEN the system SHALL output the selected point's data

#### Scenario: Render volcano plot with significance thresholds
- **WHEN** user provides fold-change and p-value columns
- **THEN** the system SHALL render a volcano plot with threshold lines
- **AND** points beyond thresholds SHALL be colored distinctly

#### Scenario: Identify significant features
- **WHEN** user hovers over a point in the volcano plot
- **THEN** the system SHALL display the feature name and statistics
- **AND** the system SHALL highlight the point

### Requirement 5: Spectrum Visualization

**User Story:** As a user, I want to visualize mass spectrometry spectra, so that I can analyze peak patterns and intensities.

#### Acceptance Criteria

1. WHEN rendering a spectrum THEN the system SHALL display m/z values on X-axis and intensity on Y-axis
2. WHEN rendering a spectrum THEN the system SHALL render peaks as vertical lines or bars
3. WHEN the user hovers over a peak THEN the system SHALL display m/z and intensity values
4. WHEN the user zooms into a region THEN the system SHALL show detailed peak information
5. WHEN multiple spectra are provided THEN the system SHALL support overlay or comparison view

#### Scenario: Render mass spectrum
- **WHEN** user provides m/z and intensity columns
- **THEN** the system SHALL render a spectrum visualization
- **AND** peaks SHALL be clearly visible and interactive

#### Scenario: Zoom into peak region
- **WHEN** user zooms into a specific m/z region
- **THEN** the system SHALL display detailed peak information
- **AND** the system SHALL maintain axis labels and scale

### Requirement 6: Interactive Selection and Brushing

**User Story:** As a user, I want to select data points or regions in visualizations, so that I can filter data and pass selections to downstream nodes.

#### Acceptance Criteria

1. WHEN the user performs a box selection THEN the system SHALL capture the selection coordinates
2. WHEN the user performs a lasso selection THEN the system SHALL identify points within the lasso path
3. WHEN the user performs a brush selection THEN the system SHALL highlight the selected region
4. WHEN selection is complete THEN the system SHALL output an event containing selected data indices or coordinates
5. WHEN the user clears selection THEN the system SHALL reset the visualization and clear the output

#### Scenario: Box select data points
- **WHEN** user drags a box around data points in a scatter plot
- **THEN** the system SHALL highlight the selected points
- **AND** the system SHALL output an event with selected point indices

#### Scenario: Lasso select data points
- **WHEN** user draws a lasso around data points
- **THEN** the system SHALL identify points within the lasso
- **AND** the system SHALL output the selection event

#### Scenario: Clear selection
- **WHEN** user clicks a clear button or presses Escape
- **THEN** the system SHALL deselect all points
- **AND** the system SHALL clear the output event

### Requirement 7: Data Mapping and Column Configuration

**User Story:** As a user, I want to configure which data columns map to visualization axes and properties, so that I can customize how data is displayed.

#### Acceptance Criteria

1. WHEN the visualization node receives data THEN the system SHALL automatically detect available columns
2. WHEN the user opens the configuration panel THEN the system SHALL display a list of available columns
3. WHEN the user selects columns for X, Y, Z axes THEN the system SHALL validate the selection and update the visualization
4. WHEN the user selects a column for color mapping THEN the system SHALL apply the color scale to the visualization
5. WHEN the user selects a column for size mapping THEN the system SHALL apply the size scale to the visualization

#### Scenario: Configure scatter plot axes
- **WHEN** user opens the configuration panel
- **THEN** the system SHALL display available columns
- **AND** user can select X, Y columns from dropdowns
- **AND** the visualization SHALL update when selections change

#### Scenario: Apply color mapping
- **WHEN** user selects a column for color mapping
- **THEN** the system SHALL apply a color scale to the visualization
- **AND** the system SHALL display a color scale legend

### Requirement 8: Data Table Node with Column Selection

**User Story:** As a user, I want to view data in a table format and select columns to pass to downstream nodes, so that I can filter and transform data in the workflow.

#### Acceptance Criteria

1. WHEN a data table node receives data THEN the system SHALL render the data in an AG-Grid table
2. WHEN the user drags a column header THEN the system SHALL allow reordering columns
3. WHEN the user selects columns THEN the system SHALL mark them for output
4. WHEN the user clicks a column header THEN the system SHALL sort the table by that column
5. WHEN the user applies a filter THEN the system SHALL filter rows based on the filter criteria
6. WHEN the user selects columns THEN the system SHALL output the selected columns as a new dataset

#### Scenario: Display data in table
- **WHEN** upstream node provides data to the table node
- **THEN** the system SHALL render the data in an AG-Grid table
- **AND** all columns SHALL be visible and sortable

#### Scenario: Select and output columns
- **WHEN** user selects specific columns
- **THEN** the system SHALL mark them for output
- **AND** the system SHALL create output ports for selected columns

#### Scenario: Filter table data
- **WHEN** user applies a filter to a column
- **THEN** the system SHALL filter the table rows
- **AND** the system SHALL update the visualization

### Requirement 9: Color Scheme Configuration

**User Story:** As a user, I want to customize color schemes for visualizations, so that I can match my preferences and improve readability.

#### Acceptance Criteria

1. WHEN the user opens color settings THEN the system SHALL display available color schemes (viridis, plasma, cool, warm, etc.)
2. WHEN the user selects a color scheme THEN the system SHALL apply it to the visualization
3. WHEN the user customizes colors THEN the system SHALL support manual color picker for specific values
4. WHEN the visualization uses categorical data THEN the system SHALL use discrete color palettes
5. WHEN the visualization uses continuous data THEN the system SHALL use continuous color gradients

#### Scenario: Select predefined color scheme
- **WHEN** user selects a color scheme from the dropdown
- **THEN** the system SHALL apply the scheme to the visualization
- **AND** the visualization SHALL update immediately

#### Scenario: Customize colors manually
- **WHEN** user opens the color picker
- **THEN** the system SHALL allow selecting custom colors
- **AND** the visualization SHALL update with custom colors

### Requirement 10: Visualization Export and Sharing

**User Story:** As a user, I want to export visualizations as images or data, so that I can share results and include them in reports.

#### Acceptance Criteria

1. WHEN the user clicks export THEN the system SHALL provide options to export as PNG, SVG, or PDF
2. WHEN the user exports as PNG THEN the system SHALL capture the current visualization state and save as image
3. WHEN the user exports data THEN the system SHALL export the underlying data in CSV or JSON format
4. WHEN the user exports THEN the system SHALL include metadata (title, axes labels, timestamp)
5. WHEN export is complete THEN the system SHALL show a success message with file location

#### Scenario: Export visualization as image
- **WHEN** user clicks export and selects PNG format
- **THEN** the system SHALL save the visualization as a PNG image
- **AND** the system SHALL show the file location

#### Scenario: Export underlying data
- **WHEN** user clicks export data
- **THEN** the system SHALL export the data in CSV format
- **AND** the system SHALL include column headers and metadata

### Requirement 11: Performance Optimization for Large Datasets

**User Story:** As a user, I want visualizations to remain responsive with large datasets, so that I can work with real mass spectrometry data without lag.

#### Acceptance Criteria

1. WHEN data contains more than 10,000 points THEN the system SHALL use data sampling or aggregation
2. WHEN the user zooms into a region THEN the system SHALL load detailed data for that region
3. WHEN the user pans THEN the system SHALL update the visualization smoothly without freezing
4. WHEN rendering large heatmaps THEN the system SHALL use virtual scrolling to maintain performance
5. WHEN memory usage exceeds threshold THEN the system SHALL warn the user and suggest data reduction

#### Scenario: Handle large scatter plot
- **WHEN** user loads a scatter plot with 100,000 points
- **THEN** the system SHALL sample or aggregate the data
- **AND** the visualization SHALL remain responsive

#### Scenario: Virtual scrolling for large heatmap
- **WHEN** user loads a heatmap with 1000×1000 cells
- **THEN** the system SHALL use virtual scrolling
- **AND** only visible cells SHALL be rendered

### Requirement 12: Visualization Node State Persistence

**User Story:** As a user, I want visualization node configurations to be saved with the workflow, so that I can reload workflows with the same visualization settings.

#### Acceptance Criteria

1. WHEN the user configures a visualization node THEN the system SHALL save all settings to the workflow JSON
2. WHEN the workflow is reloaded THEN the system SHALL restore all visualization configurations
3. WHEN the user changes a setting THEN the system SHALL update the workflow JSON immediately
4. WHEN the workflow is saved THEN the system SHALL include all visualization state in the saved file
5. WHEN the workflow is shared THEN the system SHALL preserve all visualization configurations

#### Scenario: Save visualization configuration
- **WHEN** user configures a scatter plot with specific axes and colors
- **THEN** the system SHALL save the configuration to the workflow JSON
- **AND** the configuration SHALL be restored when the workflow is reloaded

#### Scenario: Reload workflow with visualization
- **WHEN** user opens a saved workflow
- **THEN** the system SHALL restore all visualization nodes with their configurations
- **AND** the visualizations SHALL display with the same settings as before

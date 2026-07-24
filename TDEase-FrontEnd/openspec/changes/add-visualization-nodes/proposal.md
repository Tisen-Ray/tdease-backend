# Change: Add Visualization Nodes Functionality

## Why
The TDEase workflow platform needs to support interactive data visualization nodes that allow users to visualize analysis results (scatter plots, heatmaps, volcano plots, etc.) and perform interactive operations like selection/brushing. Currently, the node system lacks concrete implementations for visualization components, which are critical for the mass spectrometry data analysis workflow.

## What Changes
- Implement generic visualization node container component that can host various chart types
- Create reusable visualization components (scatter plot, heatmap, volcano plot, spectrum) with Plotly
- Implement interactive selection/brushing functionality with event output
- Create data table node component using AG-Grid with column selection and drag-drop
- Implement data mapping and column configuration UI for visualization nodes
- Add property-based tests to ensure visualization correctness across various data inputs

## Impact
- Affected specs: visualization-nodes (new capability)
- Affected code: 
  - `src/services/visualization/` - visualization service implementation
  - `src/components/nodes/` - node component implementations
  - `src/types/visualization.ts` - type definitions
  - Tests for visualization components and services

## Breaking Changes
None - this is a new capability addition.

## Dependencies
- Plotly library (already in package.json)
- AG-Grid library (already in package.json)
- Existing node system architecture

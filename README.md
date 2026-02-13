# Financial Momentum Analysis System

## Overview
This project implements a financial data analysis system designed to generate short-term momentum trading signals from historical market data. The system processes structured financial datasets, applies momentum-based logic, and produces portfolio signals with visualizations. It follows a modular MCP-style architecture that separates responsibilities across independent components.

## Project Goal
- Load and preprocess historical market data (S&P 500)
- Apply momentum-based trading logic using price returns
- Generate short-term portfolio signals (Buy/Sell/Hold)
- Visualize price movements and trading signals
- Integrate financial document (PDF) processing into the analysis workflow


## 🧠 System Architecture (MCP Design)

This project implements a **Modular Component Pattern (MCP)** architecture with three core components:

| Module | Responsibility | Key Functions |
|--------|----------------|---------------|
| **`main.py`** | 🎛️ Orchestrator | Coordinates workflow, initializes modules, manages data flow between components |
| **`finance_mcp.py`** | 💹 Financial Engine | Loads market data → Calculates momentum → Generates Buy/Sell/Hold signals → Creates portfolios |
| **`pdf_mcp.py`** | 📄 Document Processor | Extracts text from PDFs → Processes financial reports → Prepares unstructured data for analysis |

## ⚙️ How It Works

1. **Data Ingestion**  
   → `main.py` loads CSV market data from `data/`  
   → (Optional) loads PDF reports from `pdf/`

2. **Signal Generation**  
   → `finance_mcp.py` calculates momentum using rolling windows  
   → Generates signals: **Buy** (positive momentum) / **Sell** (negative momentum) / **Hold**  
   → Creates short-term portfolio allocations

3. **Document Integration**  
   → `pdf_mcp.py` extracts insights from financial reports  
   → Enables fusion of quantitative signals + qualitative document analysis

4. **Output**  
   → Signals saved as CSV in `output/`  
   → Charts visualizing price + signals saved as PNG in `output/`

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Place your data
#    - Market CSV files → data/
#    - Financial PDFs   → pdf/

# 3. Run the system
python main.py

# 4. View results in output/

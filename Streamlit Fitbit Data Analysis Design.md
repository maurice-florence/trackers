# Technical Design Specification: High-Fidelity Fitbit Health Analytics & Visualization Platform

1. Executive Summary and Architectural Vision

1.1 Project Scope and Strategic Objectives
The commoditization of biometric sensors has created a paradox in the modern health data landscape: users possess more data about their physiology than ever before, yet actionable insight remains sequestered behind proprietary algorithms and simplistic mobile interfaces. This document serves as a comprehensive, expert-level design specification for the "Quantified Self" Fitbit Analytics Platform—a custom-engineered, Python-based Streamlit application designed to dismantle these barriers.

The primary objective is to engineer a system capable of ingesting raw, granular data exports from Google Takeout, specifically targeting the local repository located at `G:\Mijn Drive\Data Analyse\00_DATA-Life_Analysis\fitbit-data`. This platform is not merely a data viewer; it is a computational engine designed to reconstruct complex proprietary metrics—such as the "Daily Readiness Score" and "Sleep Score"—using transparent, scientifically validated algorithms. Furthermore, it aims to transcend the limitations of the native Fitbit application by introducing "second-order" analytics. While standard apps display *what* happened (e.g., "You slept 6 hours"), this platform addresses *why* it happened and *how* it correlates with other lifestyle factors (e.g., "Your late-night activity consistently delays your REM onset by 45 minutes").

The target audience is the "Power User" or "Bio-hacker"—individuals who demand financial-grade analytics for their biological assets. The architectural vision prioritizes three core tenets: **Data Sovereignty**, **Algorithmic Transparency**, and **Visual Depth**.

* By processing data locally, the user retains absolute control over their sensitive health information, bypassing cloud-based aggregation layers that often obfuscate raw signal fidelity.

* By reimplementing metrics like Heart Rate Variability (HRV) based readiness in open-source Python, the system demystifies the "black box" of wearable scoring.

* Finally, by utilizing advanced plotting libraries such as Plotly Graph Objects, the application provides high-density, interactive visualizations—Poincaré plots, circadian heatmaps, and correlation matrices—that allow for exploratory data analysis far exceeding the capabilities of static mobile dashboards.

1.2 System Context and Persona Analysis

The design assumes a user persona deeply engaged with self-quantification, likely possessing a technical background or a strong affinity for data science principles. This "Analytic User" requires a tool that bridges the gap between raw CSV/JSON dumps and clinical-grade insight.

The system is designed to run in a local Windows environment, leveraging the file system performance for heavy I/O operations associated with parsing multi-gigabyte archival data. The application’s output is structured to be implemented by a developer assisted by AI coding tools (specifically GitHub Copilot). Therefore, this report creates a rigorous "prompt-ready" architecture, defining classes, data structures, and algorithmic logic with sufficient precision that an AI can generate functional code blocks with minimal hallucination.

The modular design separates concerns into distinct layers: a robust Extraction-Transformation-Loading (ETL) layer for handling the chaotic Google Takeout file structure, a Calculation Engine for deriving physiological metrics, and a Presentation Layer built on Streamlit for responsive, state-aware user interaction.

1.3 High-Level Capabilities Matrix
The platform is engineered to deliver specific capabilities that address current gaps in the wearable ecosystem. These include:

***Longitudinal Data Stitching:** The ability to merge overlapping data from multiple Google Takeout exports (e.g., a 2023 export and a 2024 export) without duplicating records, using a "Last-Write-Wins" temporal logic.

***Shadow Metric Computation:** The replication of Fitbit’s "Daily Readiness" score using raw HRV and activity data, allowing users to tweak weighting factors (e.g., prioritizing sleep over activity) to better suit their personal training loads.

***Advanced Chronobiology:** Visualization of circadian rhythm consistency using polar heatmaps, identifying "social jetlag" and behavioral drift over months or years.

***Non-Linear HRV Analysis:** Implementation of Poincaré plots to visualize autonomic nervous system balance, a feature standard in clinical HRV software (like Kubios) but absent in consumer apps.

---

1. Data Ecology and Source Forensics

The foundation of any robust analytics platform is a precise understanding of its input data. Google Takeout exports for Fitbit are notoriously complex, characterized by a fragmented file structure where a single day's data may be split across multiple JSON files or aggregated into summary CSVs. This section performs a forensic analysis of the data structures located at `G:\Mijn Drive\Data Analyse\00_DATA-Life_Analysis\fitbit-data`, defining the schema requirements for the ingestion engine.

2.1 The Directory Hierarchy of Google Takeout
The transition of Fitbit data ownership to Google has standardized the export format into the "Takeout" structure. Based on the provided research materials, the relevant data is segregated into two primary cluster types: **High-Frequency Sensor Data** and **Aggregated Summary Data**.

2.1.1 Global Export Data (The "Raw" Layer)
The directory `Takeout/Fitbit/Global Export Data/` is the critical repository for granular analysis. It contains thousands of JSON files, typically organized by metric and date. The file naming convention is generally `metric-YYYY-MM-DD.json`.

***Heart Rate (`heart_rate-*.json`):** This is the highest-volume dataset, containing sampling frequencies ranging from 1 second to 1 minute depending on the device generation and activity state.

***Schema:** The JSON structure is an array of objects.

***Forensic Note:** The `dateTime` field usually lacks a date component or timezone offset, implying it is relative to the filename's date and the user's local time settings at the moment of capture. The `confidence` field (0-3) is critical for filtering artifacts; low confidence (0-1) often indicates poor sensor contact and should be excluded from HRV calculations.

***Steps (`steps-*.json`):** These files provide intraday activity density. Unlike the daily total, these allow for the reconstruction of movement patterns throughout the day, essential for the "Circadian Fingerprint" visualization.

***Schema:** An array of objects detailing step counts over time.

***Sleep Logs (`sleep-*.json`):** These files are significantly more complex than simple duration logs. They contain a hierarchical structure detailing specific sleep stages (Wake, Light, Deep, REM) with start and end times.

***Schema:** A nested JSON object containing a `levels` dictionary. This dictionary breaks down into `summary` (total minutes per stage) and `data` (a list of every stage transition). This granularity is required to construct the "Sleep Architecture Ribbon" visualization.

2.1.2 Physical Activity & Sleep Scores (The "Summary" Layer)
Parallel to the raw data, Google exports aggregated summaries in CSV format. These are found in directories such as `Physical Activity_GoogleData` and `Sleep Score`.

***Daily Activity Summary (`Daily Activity Summary.csv`):** This file acts as the "ground truth" for daily totals. It contains columns such as Date, Calories, Steps, Distance, SedentaryMinutes, LightlyActiveMinutes, FairlyActiveMinutes, VeryActiveMinutes, and Productivity metrics.

***Utility:** This dataset is used for normalizing the raw data (e.g., ensuring the sum of minute-level steps matches the daily total) and for calculating long-term trends where minute-level precision is unnecessary.

***Sleep Score (`Sleep Score.csv`):** This CSV contains the proprietary scores calculated by Fitbit servers. Columns typically include `overall_score`, `composition_score`, `revitalization_score`, and `duration_score`.

***Utility:** These values serve as the benchmark for our "Shadow Metric" algorithms. By correlating our calculated scores against these official values, we can fine-tune our weighting coefficients.

2.2 Schema Challenges and Data Cleaning Requirements
The ingestion logic must handle several specific anomalies identified in the research:

***Timezone Ambiguity:** The raw JSONs in Global Export Data often use local time without offsets. However, the CSV summaries usually employ ISO 8601 formats with offsets. The system must create a `UserProfile` configuration allowing the user to specify their primary timezone (e.g., "Europe/Amsterdam") to localize the naive JSON timestamps correctly, ensuring alignment between heart rate data and sleep logs.

***Overlapping Data Sets:** A user managing their data locally may have multiple Takeout exports (e.g., `takeout-2023.zip` and `takeout-2024.zip`). A naive import would result in duplicate records for the overlapping periods. The system requires a "Last-Write-Wins" deduplication logic, prioritizing data from the most recent export file, which may contain server-side corrections.

***Schema Evolution:** Google occasionally alters field names (e.g., `restingHeartRate` vs `resting_heart_rate`). The parser must use robust, fuzzy matching or defined schema mapping dictionaries to handle historical variations in the export format.

---

1. Ingestion Engine Design: The ETL Pipeline
To manage the volume of data (potentially millions of heart rate rows), the application cannot parse raw JSONs on every launch. Instead, it must implement a formal Extract-Transform-Load (ETL) pipeline that converts raw files into an optimized columnar format (Parquet).

3.1 The FitbitLoader Class Architecture
The core of the ingestion layer is the `FitbitLoader` class. This class is responsible for traversing the directory structure, identifying valid data files, and managing the extraction process.

**Design Pattern:**
The loader should utilize a generator-based approach for file discovery to minimize memory overhead before processing. It will rely on `os.walk` to traverse the `G:\Mijn Drive...` path recursively.

> **Copilot Implementation Prompt Structure:**
> "Create a Python class named FitbitLoader. The `__init__` method should accept a `root_path` string. Implement a method `_discover_files(pattern)` using `os.walk` and `fnmatch` to yield file paths matching a specific pattern (e.g., `heart_rate-*.json`). Implement error handling to skip corrupted JSON files and log the error.">>
3.2 Parsing Strategy: High-Frequency Data
Parsing minute-level or second-level heart rate data is the computational bottleneck of the system.

**Optimization Strategy:**
***Batch Processing:** Instead of appending rows to a DataFrame inside a loop (which is  complexity), the system should accumulate dictionary objects in a list and create the DataFrame in a single operation ().

***Vectorized Timestamp Conversion:** Using `pd.to_datetime` on millions of string rows is slow. The parser should use `pd.to_datetime(..., format=...)` with an explicit format string to speed up parsing by up to 50x compared to inferring the format.

* **Type Casting:** Downcast numeric columns immediately. Heart rate (BPM) should be cast to `uint8` (0-255 range) rather than the default `int64`, saving 87.5% of memory for that column.

> **Copilot Implementation Prompt Structure:**
> "Implement a function `parse_heart_rate` in the `FitbitLoader` class. It should iterate through the discovered JSON files. For each file, extract the date from the filename to serve as the base date. Iterate through the 'value' array, parsing 'time' and 'bpm'. Store result in a list of dicts. Convert to Pandas DataFrame. Ensure 'dateTime' is the index. Downcast 'bpm' to uint8. Handle the case where the JSON structure changes from list-of-dicts to dict-of-lists.">>
3.3 The Deduplication Logic (The "Smart Merge")
Handling the overlap between multiple export archives is critical for data integrity. The logic must ensure that if a user has exports from June and July, the June data present in the July export (if any) overwrites the older version, or vice versa, depending on the timestamp validity.

**Algorithm:**
1.**Concatenation:** Load all new data into a temporary DataFrame.

2.**Sorting:** Sort the DataFrame by the index (`dateTime`).

1. **Deduplication:** Apply `df = df[~df.index.duplicated(keep='last')]`. The `keep='last'` parameter ensures that if two records exist for 2024-01-01 12:00:00, the one parsed later (typically from a newer file if the file list is sorted) is preserved.

3.4 Storage Layer: Parquet Integration
To satisfy the requirement of a responsive Streamlit app, the ETL pipeline must serialize the processed DataFrames to disk. Parquet is the ideal format due to its columnar compression schemes (Snappy or Zstd), which work exceptionally well with time-series data where values (like sleep stages) repeat frequently.

**Implementation Details:**
***Partitioning:** For the Heart Rate dataset, partitioning by Year and Month (e.g., `processed_data/hr/year=2024/month=01/data.parquet`) is recommended to allow the application to load only specific time ranges ("Lazy Loading") rather than the entire history.

***Library:** The system should utilize `pyarrow` as the engine for Pandas `to_parquet` and `read_parquet` functions for maximum performance.

---

1. Physiological Modeling: The "Shadow" Metric Engine
This section details the theoretical and algorithmic reconstruction of Fitbit's proprietary metrics. By implementing these "Shadow Metrics," the platform provides transparency and allows the user to understand the physiological drivers of their scores.

4.1 Daily Readiness Score Reconstruction
Fitbit's Daily Readiness Score is a composite metric derived from three domains: **Heart Rate Variability (HRV)**, **Sleep Debt**, and **Recent Activity (Fatigue)**. The "Shadow Readiness" algorithm will mimic this structure using a weighted Z-score approach.

4.1.1 The Theoretical Model
The score  is calculated as a weighted sum of normalized component scores ():

Where the weights are customizable but default to:
"""Technical Design Specification: High-Fidelity Fitbit Health Analytics & Visualization Platform"""

## 1 Executive Summary and Architectural Vision

### 1.1 Project Scope and Strategic Objectives

The commoditization of biometric sensors has increased access to physiological data while actionable insight remains limited by proprietary algorithms and simplified mobile interfaces. This document specifies the "Quantified Self" Fitbit Analytics Platform — a Python/Streamlit application to increase transparency and enable advanced analysis.

The platform ingests Google Takeout exports from `G:\Mijn Drive\Data Analyse\00_DATA-Life_Analysis\fitbit-data`. It reconstructs metrics such as Daily Readiness and Sleep Score using open algorithms and offers second-order analytics that explain correlations (for example, how late-night activity affects REM onset).

Target audience: technically inclined power users. Architectural priorities: **Data Sovereignty**, **Algorithmic Transparency**, **Visual Depth**.

Key principles:

* Local processing to keep sensitive data private.
* Open implementations of HRV and readiness metrics.
* High-density interactive visualizations (Plotly) for deep exploratory analysis.

### 1.2 System Context and Persona Analysis

The user is expected to be comfortable with CSV/JSON and basic data science concepts. The app targets local Windows environments for performant I/O. The architecture is modular: ETL, calculation engine, and Streamlit presentation layer.

### 1.3 High-Level Capabilities

* Longitudinal data stitching with Last-Write-Wins deduplication.
* Shadow metric computation for Readiness and Sleep Score with tunable weights.
* Chronobiology visualizations (polar heatmaps) to identify social jetlag.
* Non-linear HRV analysis (Poincaré plots).

---

## 2 Data Ecology and Source Forensics

Google Takeout Fitbit exports are fragmented. A robust ingestion pipeline must handle multiple JSON files per day and aggregated CSV summaries.

### 2.1 Directory Hierarchy

Two primary clusters: **High-Frequency Sensor Data** (raw JSONs) and **Aggregated Summary Data** (CSVs).

#### 2.1.1 Global Export Data (Raw Layer)

`Takeout/Fitbit/Global Export Data/` typically contains files like `metric-YYYY-MM-DD.json`.

* Heart Rate (`heart_rate-*.json`): array of objects; sampling from 1 s to 1 min. `dateTime` may lack timezone; `confidence` (0–3) should be used to filter data for HRV.
* Steps (`steps-*.json`): minute-level step counts for intraday reconstruction.
* Sleep Logs (`sleep-*.json`): nested `levels` with `summary` and `data` stage transitions.

#### 2.1.2 Summary Layer

* Daily Activity Summary (`Daily Activity Summary.csv`): daily totals used for normalization and trend analysis.
* Sleep Score (`Sleep Score.csv`): Fitbit's proprietary scores used as benchmarks for tuning shadow metrics.

### 2.2 Schema Challenges

* Timezone ambiguity: provide a `UserProfile.timezone` to localize naive timestamps.
* Overlapping exports: deduplicate using Last-Write-Wins semantics.
* Schema evolution: use a mapping dictionary to handle field-name variations.

---

## 3 Ingestion Engine Design: ETL Pipeline

Convert raw JSONs to Parquet and avoid parsing raw files on every launch.

### 3.1 FitbitLoader

`FitbitLoader` should discover files with `os.walk` + `fnmatch`, gracefully skip corrupted JSONs, and yield file paths via a generator.

Example Copilot prompt: create `FitbitLoader` with `_discover_files(pattern)`.

### 3.2 Parsing Strategy

Optimizations:

* Batch processing: collect dicts and create a DataFrame once.
* Use `pd.to_datetime(..., format=...)` to speed parsing.
* Downcast numeric columns (e.g., `bpm` → `uint8`).

Implement `parse_heart_rate` to extract `dateTime` and `bpm`, set `dateTime` as the index, and handle alternate JSON structures.

### 3.3 Deduplication (Smart Merge)

Load new data, sort by `dateTime`, then `df = df[~df.index.duplicated(keep='last')]` so newer records overwrite older ones.

### 3.4 Storage: Parquet

Write processed data to Parquet using `pyarrow`. Partition heart-rate data by year/month for lazy loading.

---

## 4 Physiological Modeling: Shadow Metric Engine

Recreate proprietary metrics with transparent, tunable algorithms.

### 4.1 Daily Readiness

Shadow Readiness combines HRV, Sleep, and Fatigue into a weighted score.

#### 4.1.1 Model

Let normalized components be $z_{HRV}$, $z_{Sleep}$, $z_{Fatigue}$. Then

$$
S = w_{HRV} z_{HRV} + w_{Sleep} z_{Sleep} + w_{Fatigue} z_{Fatigue}
$$

Defaults: $w_{HRV}=0.5, w_{Sleep}=0.3, w_{Fatigue}=0.2$.

#### 4.1.2 Components

* HRV ($z_{HRV}$): use rMSSD from IBI if available; otherwise proxy with inverse RHR trend. Normalize to 0–100 and clip values >100.
* Sleep ($z_{Sleep}$): map Total Sleep Time relative to user need to 0–100.
* Fatigue ($z_{Fatigue}$): compute ACWR using Load = Activity Calories + Active Zone Minutes. If $ACWR>1.5$, apply a penalty; normalize to 0–100.

Copilot prompt: `calculate_readiness(df)` should compute EMAs for baselines, normalize, apply weights, forward-fill missing baselines, and return `shadow_readiness_score`.

### 4.2 Sleep Score

Decompose into Duration (50), Quality (25), Restoration (25).

* Duration: use a logistic or piecewise function where <3h→0 and meeting goal (default 8h) yields 50 points.
* Quality: calculate percentages of Deep and REM; targets Deep 15–20%, REM 20–25%; scale 0–25.
* Restoration: Restoration Gap = RHR − Avg(SleepHR). Map gap to 0–25 (positive gap increases score).

Algorithm: extract sleep window, compute Avg(SleepHR), retrieve RHR, compute gap, map to restoration score.

---

## 5 Advanced Visualization Engineering

Leverage Plotly for high-density interactive visuals.

### 5.1 Circadian Polar Heatmap (Life Fingerprint)

Resample into 15-minute bins, pivot by date and time-of-day, map time→degrees, date→radius, and use `go.Barpolar` with a `Viridis` colorscale.

### 5.2 HRV Poincaré

Plot successive IBIs: x = $IBI_n$, y = $IBI_{n+1}$, overlay ellipse from SD1/SD2, use low opacity scatter for density.

### 5.3 Sleep Architecture Ribbon

Render stage transitions as horizontal stacked bars per date. Color map: Wake=#FF0000, REM=#00FFFF, Deep=#00008B, Light=#ADD8E6.

### 5.4 Lifestyle Correlation Matrix

Merge daily metrics and compute Pearson correlations (`df.corr()`); render a diverging heatmap (red→white→blue).

---

## 6 Application Architecture & State Management

Use `@st.cache_data` / `@st.cache_resource` and `st.session_state` to avoid reloading large datasets on every interaction.

Example:

```python
@st.cache_data(ttl=3600, show_spinner="Parsing Fitbit Archive...")
def load_master_dataframe(path):
    loader = FitbitLoader(path)
    return loader.process_all()
```

Store UI filters in `st.session_state`.

### 6.2 Directory Structure

@st.cache_data(ttl=3600, show_spinner="Parsing Fitbit Archive...")
def load_master_dataframe(path):
    loader = FitbitLoader(path)
    return loader.process_all()

```bash
fitbit-analytics/
├── app.py
├── requirements.txt
├── config.py
├── src/
│   ├── ingestion.py
│   ├── processing.py
│   ├── algorithms.py
│   ├── visuals.py
│   └── components.py
└── assets/
    └── style.css
```

### 6.3 UI/UX

* Metric cards, tabs (`Overview`, `Sleep Lab`, `Metabolic`, `Correlations`, `Raw Data`).

---

## 7 Implementation Roadmap & Copilot Prompts

Prompts for ingestion, metrics, visuals, and app scaffolding are included to help AI-assisted generation.

## 8 Conclusion

This spec describes how to build a local, transparent health analytics platform that reproduces and extends Fitbit metrics.

### Data Dictionary

| File Type | Path Pattern | Key Fields Needed | Data Frequency |
| --- | --- | --- | --- |
| Heart Rate | `Global Export Data/heart_rate-*.json` | `value.bpm`, `value.confidence` | 1 s - 1 min |
| Steps | `Global Export Data/steps-*.json` | `value` (count) | 1 min |
| Sleep Details | `Global Export Data/sleep-*.json` | `levels.data` (stage, seconds) | event-based |
| Daily Activity | `Physical Activity.../Daily Activity Summary.csv` | Resting Heart Rate, Steps, Calories | daily |
| Official Scores | `Sleep Score/Sleep Score.csv` | `overall_score`, `deep_sleep_minutes` | daily |

### Comparison of Metrics

| Metric | Fitbit (Proprietary) | Shadow App (Python) | Advantage |
| --- | --- | --- | --- |
| Readiness | Black box | Weighted Z-score (open) | tunable weights |
| Restoration | Sleeping HR < RHR | RHR − Avg(SleepHR) | transparent |
| Sleep Score | Proprietary 0–100 | Logistic/parametric | customizable goals |

---

## Works Cited

* Fitbit Community: <https://community.fitbit.com/t5/Product-Feedback/Able-to-select-which-data-to-export-and-date-range-after-Google-migration/idi-p/5483105>
* Google Help: <https://support.google.com/fitbit/answer/14236615?hl=en>
* Parsing Fitbit HR from Google Takeout — Medium: <https://medium.com/@abhik.ch6/parsing-fitbit-hr-from-google-takeout-9d9e98ce6aee>

---

Would you like me to (a) save a cleaned branch-ready copy, (b) run a markdown linter, or (c) rephrase any section?
***Metric Cards:** Use custom HTML/CSS cards (via `st.markdown`) to display top-level KPIs (Readiness, RHR, HRV) with large fonts and "Delta" arrows (green/red) indicating change from the baseline.

***Tabbed Layout:** Use `st.tabs` to segregate the application into logical workflows:

***Overview:** The "Morning Briefing" (KPIs + Readiness Gauge).

***Sleep Lab:** Deep dive into the Ribbon charts and Restoration analysis.

***Metabolic:** Heart Rate Zones, Activity heatmaps, and VO2 Max trends.

***Correlations:** The "Data Science" tab with Matrices and Poincaré plots.

***Raw Data:** A tabular view for inspection and export.

---

1. Implementation Roadmap & Copilot Prompts
This section provides the actionable "blueprints" for the developer to use with AI coding assistants. These prompts are structured to provide enough context for the AI to generate near-perfect code.

7.1 Module 1: Data Ingestion (`src/ingestion.py`)
**Context:** "We are building a Fitbit Analysis app. We need to parse 'Global Export Data' JSONs."
>> **Prompt:** "Write a Python class `FitbitLoader`. It should have a method `load_heart_rate(path)` that searches recursively for `heart_rate-*.json`. Use `json.load` to parse files. The JSON contains a 'value' key which is a list of dicts `{'dateTime': '...', 'value': {'bpm': 123, 'confidence': 2}}`. Extract these into a Pandas DataFrame. Convert 'dateTime' to datetime objects. Handle errors where the file might be empty. Return a dataframe sorted by time.">>
7.2 Module 2: Metric Algorithms (`src/algorithms.py`)
**Context:** "We need to calculate a daily readiness score based on HRV and Sleep."
>> **Prompt:** "Create a function `calculate_shadow_readiness(df_daily)`. The input dataframe has columns `rmssd`, `total_sleep_min`, and `activity_cal`. Calculate a rolling 14-day mean for rmssd and total_sleep_min. Create a normalized score for HRV: `(current_rmssd / rolling_rmssd) * 100`. Create a normalized score for Sleep: `(current_sleep / rolling_sleep) * 100`. Return a weighted average: `0.5 * HRV_Score + 0.3 * Sleep_Score + 0.2 * (Activity_Score)`. Ensure the final score is capped at 100.">>
7.3 Module 3: Visualization (`src/visuals.py`)
**Context:** "We need a Plotly Polar Heatmap for circadian rhythms."
>> **Prompt:** "Write a function `plot_polar_activity(df)`. The input `df` has a DatetimeIndex and a `steps` column. Create columns for `date` and `time_of_day` (in minutes). Convert `time_of_day` to degrees (0-360). Use `go.Barpolar` to plot. Map `r` to `date`, `theta` to degrees, and `marker_color` to `steps`. Apply a dark template and remove the radial axis labels.">>
7.4 Module 4: The Streamlit App (`app.py`)
**Context:** "Main dashboard entry point."
>> **Prompt:** "Create a Streamlit app structure. Use `st.set_page_config(layout='wide')`. In the sidebar, add a text input for 'Data Path' defaulting to `G:\Mijn Drive\Data Analyse\00_DATA-Life_Analysis\fitbit-data`. Add a `st.cache_data` function to call our `FitbitLoader`. Create tabs: 'Overview', 'Sleep', 'Activity'. In 'Overview', display 3 metric cards using `st.columns`.">>
---

1. Conclusion
This design specification outlines a pathway to transform a static collection of Fitbit JSON files into a dynamic, living health dashboard. By acknowledging the specific constraints of the Google Takeout format and leveraging the power of Python's data science stack, this application allows the user to reclaim agency over their biological data.

The resulting system is not just a reproduction of the Fitbit Premium experience ; it is an enhancement, offering the transparency and depth required by the modern "Quantified Self" practitioner. The use of "Shadow Metrics" validates the proprietary scores, while the advanced visualizations provide the diagnostic capability to optimize lifestyle choices based on hard data.

Table 1: Data Dictionary for Key File Types
The following table illustrates the schema elements necessary for data parsing:

| File Type | Path Pattern | Key Fields Needed | Data Frequency |
| --- | --- | --- | --- |
| Heart Rate | `Global Export Data/heart_rate-*.json` | `value.bpm, value.confidence` | 1 sec - 1 min |
| Steps | `Global Export Data/steps-*.json` | `value` (count) | 1 min |
| Sleep Details | `Global Export Data/sleep-*.json` | `levels.data` (stage, seconds) | Event-based |
| Daily Activity | `Physical Activity.../Daily Activity Summary.csv` | Resting Heart Rate, Steps, Calories | Daily |
| Official Scores | `Sleep Score/Sleep Score.csv` | `overall_score`, `deep_sleep_minutes` | Daily |

Table 2: Comparison of Metrics
The following table outlines the system's analytical advancements:

| Metric | Fitbit (Proprietary) | "Shadow" App (Python) | Advantage of Shadow |
| --- | --- | --- | --- |
| Readiness | Black Box (HRV + Sleep + Activity) | Weighted Z-Score (Open Source) | User can adjust weights (e.g., ignore activity if injured). |
| Restoration | Sleeping HR < RHR | RHR - Avg(SleepHR) | Transparent calculation logic. |
| Sleep Score | 0-100 Scale | Logistic Decay Function | Customizable "Goal" (e.g., 9 hours vs 7 hours). |

---

Works Cited

* Able to select which data to export and date range after Google migration - Fitbit Community, accessed February 17, 2026, [https://community.fitbit.com/t5/Product-Feedback/Able-to-select-which-data-to-export-and-date-range-after-Google-migration/idi-p/5483105](https://community.fitbit.com/t5/Product-Feedback/Able-to-select-which-data-to-export-and-date-range-after-Google-migration/idi-p/5483105)

* How do I export my Fitbit data? - Google Help, accessed February 17, 2026, [https://support.google.com/fitbit/answer/14236615?hl=en](https://support.google.com/fitbit/answer/14236615?hl=en)

* Parsing Fitbit HR from Google Takeout | by Abhik Chowdhury - Medium, accessed February 17, 2026, [https://medium.com/@abhik.ch6/parsing-fitbit-hr-from-google-takeout-9d9e98ce6aee](https://medium.com/@abhik.ch6/parsing-fitbit-hr-from-google-takeout-9d9e98ce6aee)

* Google download of Fitbit data give absolute garbage data : r/fitbit - Reddit, accessed February 17, 2026, [https://www.reddit.com/r/fitbit/comments/1mhns8v/google_download_of_fitbit_data_give_absolute/](https://www.reddit.com/r/fitbit/comments/1mhns8v/google_download_of_fitbit_data_give_absolute/)

* Fitbit Daily Data Export Format - MyDataHelps Designer User Guide, accessed February 17, 2026, [https://support.mydatahelps.org/fitbit-daily-data-export-format?hsLang=en](https://support.mydatahelps.org/fitbit-daily-data-export-format?hsLang=en)

* Sleep Data from FitBit Tracker - Kaggle, accessed February 17, 2026, [https://www.kaggle.com/datasets/riinuanslan/sleep-data-from-fitbit-tracker](https://www.kaggle.com/datasets/riinuanslan/sleep-data-from-fitbit-tracker)

* Removing duplicate data in Pandas - wrighters.io, accessed February 17, 2026, [https://www.wrighters.io/removing-duplicate-data-in-pandas/](https://www.wrighters.io/removing-duplicate-data-in-pandas/)

* Removing duplicate records from CSV file using Python Pandas - Stack Overflow, accessed February 17, 2026, [https://stackoverflow.com/questions/52633819/removing-duplicate-records-from-csv-file-using-python-pandas](https://stackoverflow.com/questions/52633819/removing-duplicate-records-from-csv-file-using-python-pandas)

* What's my readiness score in the Fitbit app - Google Help, accessed February 17, 2026, [https://support.google.com/fitbit/answer/14236710?hl=en](https://support.google.com/fitbit/answer/14236710?hl=en)

* Daily Readiness Score - Google Store, accessed February 17, 2026, [https://store.google.com/gb/magazine/fitbit_daily_readiness_score?hl=en-GB](https://store.google.com/gb/magazine/fitbit_daily_readiness_score?hl=en-GB)

* How Does Fitbit Track Sleep and What is the Fitbit Sleep Score? - Fitbit Enterprise, accessed February 17, 2026, [https://fitbit.google/enterprise/blog/track-sleep/](https://fitbit.google/enterprise/blog/track-sleep/)

* How your Fitbit sleep score is calculated - Android Police, accessed February 17, 2026, [https://www.androidpolice.com/fitbit-sleep-score-calculation-explainer/](https://www.androidpolice.com/fitbit-sleep-score-calculation-explainer/)

* 2.5. Nonlinear Module — pyHRV - OpenSource Python Toolbox for Heart Rate Variability 0.4 documentation, accessed February 17, 2026, [https://pyhrv.readthedocs.io/en/latest/_pages/api/nonlinear.html](https://pyhrv.readthedocs.io/en/latest/_pages/api/nonlinear.html)

* HRV/poincare.py at master · pickus91/HRV - GitHub, accessed February 17, 2026, [https://github.com/pickus91/HRV/blob/master/poincare.py](https://github.com/pickus91/HRV/blob/master/poincare.py)

* st.metric - Streamlit Docs, accessed February 17, 2026, [https://docs.streamlit.io/develop/api-reference/data/st.metric](https://docs.streamlit.io/develop/api-reference/data/st.metric)

---

Would you like me to make any adjustments to the formatting, such as tweaking the visual presentation of the prompts or data tables?

import os
from datetime import datetime

import streamlit as st
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load local environmental variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# Page Title & Layout Configurations
st.set_page_config(page_title="Regal Calibration Registry", layout="wide")

# Title Banner
st.title(" ^‿^ Regal Calibration Audit System ^‿^")
st.markdown("### Search and verify asset calibration logs instantaneously.")
st.divider()

#  Secure & Optimized Database Connection Engine
@st.cache_resource
def init_connection():
    """Maintains a single persistent connection pool to CalTest."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "CalTest"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD")
    )

try:
    conn = init_connection()
except Exception as e:
    st.error(f"❌ Database Connection Failure: {e}")
    st.stop()

def get_all_calibration_tables():
    """Queries Postgres system logs to fetch all custom data tables automatically."""
    query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """
    with conn.cursor() as cur:
        cur.execute(query)
        tables = [row[0] for row in cur.fetchall()]
                
    return sorted(tables)


def get_table_date_column(table_name):
    """Find the best date column for a table, accounting for different workbook templates."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position;
            """,
            (table_name,),
        )
        columns = [row[0] for row in cur.fetchall()]

    if not columns:
        return None

    for column_name in columns:
        lowered = column_name.lower()
        if lowered in {"date_calibrated", "calibration_date", "date"} or lowered.endswith("_date") or lowered.startswith("date_"):
            return column_name

    for column_name in columns:
        if "date" in column_name.lower():
            return column_name

    return None


def resolve_field_value(data_dict, aliases):
    """Return the first present value for a field using several possible column aliases."""
    for alias in aliases:
        value = data_dict.get(alias)
        if value not in (None, ""):
            return value
    return None


# Fetch all available asset tables dynamically
refresh_tables = st.sidebar.button("🔄 Refresh asset list")
if refresh_tables:
    st.session_state["available_tables"] = get_all_calibration_tables()

if "available_tables" not in st.session_state:
    st.session_state["available_tables"] = get_all_calibration_tables()

available_tables = st.session_state["available_tables"]

if not available_tables:
    st.warning("⚠️ No active asset tables found in the 'CalTest' public schema. Run your import script first.")
    st.stop()

# Interactive Table Selection Slicer (Now 100% Dynamic!)
target_table = st.selectbox(
    "Select Asset Category:",
    options=available_tables,
    format_func=lambda x: x.replace("calibration_", "").replace("_", " ").upper()
)

# 🔍 The Auditor Search Bar
search_serial = st.text_input("🔍 Enter Gauge Serial Number to Audit:", placeholder="e.g. 26477").strip()

if search_serial:
    date_column = get_table_date_column(target_table)

    if not date_column:
        st.warning(f"⚠️ No usable date column found for table '{target_table}'.")
        st.stop()

    # 1. First, fetch ALL available calibration dates for this specific serial number
    date_query = sql.SQL(
        "SELECT {field} FROM public.{table} WHERE serial_number = %s ORDER BY {field} DESC;"
    ).format(
        field=sql.Identifier(date_column),
        table=sql.Identifier(target_table),
    )

    with conn.cursor() as cur:
        cur.execute(date_query, (search_serial,))
        all_dates = [row[0] for row in cur.fetchall()]

    if all_dates:
        # 2. Put a clean date selector right below the search bar if multiple histories exist
        formatted_dates = [d.strftime("%Y-%m-%d") for d in all_dates]
        selected_date_str = st.selectbox("📅 Select Calibration Historical Record to View:", options=formatted_dates)
        selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()

        # 3. Pull the exact row profile matching the Serial Number + Selected Date
        query = sql.SQL(
            "SELECT * FROM public.{table} WHERE serial_number = %s AND {field} = %s;"
        ).format(
            field=sql.Identifier(date_column),
            table=sql.Identifier(target_table),
        )

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (search_serial, selected_date))
            result = cur.fetchone()
            
        if result:
            st.success(f"✅ Record Found for Serial Number: {search_serial} [{selected_date_str}]")
            
            # Split screen into visual layout cards
            col1, col2 = st.columns(2)
            data_dict = {k.lower(): v for k, v in result.items()}
            
            with col1:
                st.subheader("📋 Asset Identity Details")
                gage_type = resolve_field_value(data_dict, ['gage_type', 'type', 'gauge_type'])
                manufacturer = resolve_field_value(data_dict, ['manufacturer', 'mfg', 'gauge_manufacturer'])
                model_number = resolve_field_value(data_dict, ['model_number', 'model', 'gauge_desc', 'description', 'desc'])
                graduation = resolve_field_value(data_dict, ['graduation', 'size', 'go_tol', 'no_go_tol', 'go_range', 'no_go_range'])
                calibrated_by = resolve_field_value(data_dict, ['calibrated_by', 'inspector', 'inspected'])

                st.write(f"**Gage Type:** {gage_type if gage_type is not None else 'N/A'}")
                st.write(f"**Manufacturer / Mfg:** {manufacturer if manufacturer is not None else 'N/A'}")
                st.write(f"**Model Number:** {model_number if model_number is not None else 'N/A'}")
                st.write(f"**Graduation/Size:** {graduation if graduation is not None else 'N/A'}")
                st.write(f"**Inspector / Calibrated By:** {calibrated_by if calibrated_by is not None else 'N/A'}")
                date_label = date_column.replace('_', ' ').title()
                st.write(f"**{date_label}:** {data_dict.get(date_column.lower(), 'N/A')}")
                st.write(f"**Last Sync Updated:** {data_dict.get('updated_at', 'N/A')}")
                
            with col2:
                st.subheader("🔬 Calibration System Parameters")
                st.write(f"**Procedure Key:** {data_dict.get('procedure_name', data_dict.get('procedure_used', 'N/A'))}")
                st.write(f"**Master S/N Used:** {data_dict.get('sn_gage_used_to_cal', data_dict.get('sn_of_gage_used_to_calibrate', 'N/A'))}")
                
                # 📅 Display the manual next due date from Excel
                next_due = data_dict.get('next_due_date', data_dict.get('next_calibration_due', 'N/A'))
                st.write(f"**Next Calibration Due:** {next_due}")
                
                # 🟢 Manual/Dynamic Operational Status Card
                status_val = str(data_dict.get('finding', data_dict.get('status', 'READY'))).upper()
                if any(word in status_val for word in ["READY", "PASS", "ACCEPT"]):
                    st.metric(label="ASSET OPERATIONAL STATUS", value=status_val, delta="Passed Inspection")
                else:
                    st.metric(label="ASSET OPERATIONAL STATUS", value=status_val, delta="Requires Attention", delta_color="inverse")
                    
            # 📊 Dynamic Trial Run Matrix Parser
            trial_1_data = {}
            trial_2_data = {}
            trial_3_data = {}
            
            for col_name, col_value in data_dict.items():
                if col_name.endswith('_1') or col_name.endswith('_trial_1'):
                    nominal = col_name.replace('_trial_1', '').replace('_1', '').replace('_', '.')
                    trial_1_data[nominal] = col_value
                elif col_name.endswith('_2') or col_name.endswith('_trial_2'):
                    nominal = col_name.replace('_trial_2', '').replace('_2', '').replace('_', '.')
                    trial_2_data[nominal] = col_value
                elif col_name.endswith('_3') or col_name.endswith('_trial_3'):
                    nominal = col_name.replace('_trial_3', '').replace('_3', '').replace('_', '.')
                    trial_3_data[nominal] = col_value

            if trial_1_data:
                st.divider()
                with st.expander("👁️ View Full Raw Trial Run Spreadsheet Matrix", expanded=True):
                    sorted_nominals = sorted(trial_1_data.keys(), key=lambda x: float(x) if x.replace('.','',1).isdigit() else x)
                    matrix_data = {
                        "Checkpoint Nominal": sorted_nominals,
                        "Trial 1 Reading": [trial_1_data[n] for n in sorted_nominals],
                        "Trial 2 Reading": [trial_2_data.get(n, None) for n in sorted_nominals],
                        "Trial 3 Reading": [trial_3_data.get(n, None) for n in sorted_nominals]
                    }
                    st.table(matrix_data)
                
    else:
        st.warning(f"⚠️ No active calibration history found for Serial Number: '{search_serial}'")

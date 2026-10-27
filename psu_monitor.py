import serial
import time

# --- CONFIGURATION ---
PORT = 'COM4'       # UART Port
BAUDRATE = 9600     # Must match UART_BAUDRATE in firmware
TIMEOUT = 0.5       # UART Read timeout in seconds
POLL_INTERVAL = 0.5 # Frequency of polling

def send_query(ser, command):
    """Sends a SCPI command and reads the response if it's a query."""
    full_command = f"{command}\n".encode('ascii')
    ser.write(full_command)
    
    if "?" in command or command.startswith("*"):
        response = ser.readline().decode('ascii').strip()
        return response
    return None

def parse_response(response):
    """Parses response and handles SCPI error codes."""
    if not response:
        return "N/A"
    
    if response.startswith("ERR:"):
        code = response.replace("ERR:", "").strip()
        if "109" in code:
            return "Err: Missing Param"
        elif "113" in code:
            return "Err: Undefined Head"
        else:
            return f"Err: Code {code}"
            
    return response

def format_value(val, format_str="{:.3f}"):
    """Safely converts string to float and formats it (SI units)."""
    parsed = parse_response(val)
    if "Err" in parsed or parsed == "N/A":
        return parsed
    try:
        return format_str.format(float(parsed))
    except ValueError:
        return "Parse Err"

def main():
    print(f"Connecting to Power Supply on {PORT}...")
    try:
        with serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT) as ser:
            time.sleep(2) # Wait for connection to stabilize
            
            # Read Identification
            idn = send_query(ser, "*IDN?")
            print(f"Connected to: {idn}\n")
            
            # Table Header with formatted columns
            print(
                f"{'OUTP':<4} | {'MODE':<4} | "
                f"{'SET_V (RAW)':<16} | {'SET_I (RAW)':<16} | "
                f"{'MEAS_V (RAW)':<16} | {'MEAS_I (RAW)':<16} | "
                f"{'POWER':<10} | {'ENERGY':<12}"
            )
            print("-" * 122)
            
            while True:
                # 1. Fetch current settings
                set_v = send_query(ser, "SOUR:VOLT?")
                raw_set_v = send_query(ser, "SOUR:VOLT:RAW?")
                set_i = send_query(ser, "SOUR:CURR?")
                raw_set_i = send_query(ser, "SOUR:CURR:RAW?")
                outp = send_query(ser, "OUTP?")
                
                # 2. Fetch active multimeter measurements
                meas_v = send_query(ser, "MEAS:VOLT?")
                raw_v = send_query(ser, "MEAS:VOLT:RAW?")
                meas_i = send_query(ser, "MEAS:CURR?")
                raw_i = send_query(ser, "MEAS:CURR:RAW?")
                power = send_query(ser, "MEAS:POW?")
                energy = send_query(ser, "MEAS:ENER?")
                mode = send_query(ser, "MEAS:MODE?")
                
                # 3. Process output state string
                outp_parsed = parse_response(outp)
                outp_str = "ON" if outp_parsed == "1" else "OFF" if outp_parsed == "0" else outp_parsed
                
                # 4. Format values in SI units
                v_set_str = format_value(set_v, "{:.3f} V")
                raw_set_v_str = parse_response(raw_set_v)
                
                i_set_str = format_value(set_i, "{:.3f} A")
                raw_set_i_str = parse_response(raw_set_i)
                
                v_meas_str = format_value(meas_v, "{:.3f} V")
                raw_v_str = parse_response(raw_v)
                
                i_meas_str = format_value(meas_i, "{:.3f} A")
                raw_i_str = parse_response(raw_i)
                
                p_str = format_value(power, "{:.3f} W")
                e_str = format_value(energy, "{:.3f} Wh") 
                mode_str = parse_response(mode)
                
                # 5. Combine values with raw counterparts
                set_v_column = f"{v_set_str} ({raw_set_v_str})"
                set_i_column = f"{i_set_str} ({raw_set_i_str})"
                meas_v_column = f"{v_meas_str} ({raw_v_str})"
                meas_i_column = f"{i_meas_str} ({raw_i_str})"
                
                # Print and rewrite the line in terminal using carriage return (\r)
                print(
                    f"{outp_str:<4} | {mode_str:<4} | "
                    f"{set_v_column:<16} | {set_i_column:<16} | "
                    f"{meas_v_column:<16} | {meas_i_column:<16} | "
                    f"{p_str:<10} | {e_str:<12}", 
                    end="\r"
                )
                
                time.sleep(POLL_INTERVAL)

    except serial.SerialException as e:
        print(f"\nSerial error: {e}")
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")

if __name__ == "__main__":
    main()
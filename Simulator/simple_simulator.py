#!/usr/bin/env python3
"""Simple Serial Simulator - Send and Receive data via COM15."""

import sys
import serial
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
import queue
from datetime import datetime

class SimpleSerialSimulator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Simple Serial Simulator - COM15 (Send & Receive)")
        self.root.geometry("700x600")
        
        self.serial_port = None
        self.receiving = False
        self.receive_thread = None
        self.send_queue = queue.Queue()
        self._send_thread = threading.Thread(target=self.send_loop, daemon=True)
        self._send_thread.start()
        self.setup_ui()
        
    def setup_ui(self):
        """Create simple UI with buttons and log."""
        # Status label
        self.status_label = tk.Label(self.root, text="Disconnected", fg="red", font=("Arial", 12, "bold"))
        self.status_label.pack(pady=5)
        
        # Connection frame
        conn_frame = tk.Frame(self.root)
        conn_frame.pack(pady=5)
        
        tk.Button(conn_frame, text="Connect COM15", command=self.connect_serial, bg="lightgreen").pack(side=tk.LEFT, padx=5)
        tk.Button(conn_frame, text="Disconnect", command=self.disconnect_serial, bg="lightcoral").pack(side=tk.LEFT, padx=5)
        
        # Receiving status
        self.receive_label = tk.Label(self.root, text="Not Receiving", fg="orange")
        self.receive_label.pack()
        
        # Control buttons frame
        control_frame = tk.LabelFrame(self.root, text="Feedback Controls", padx=10, pady=10)
        control_frame.pack(pady=10, padx=10, fill="x")
        
        # ARM buttons
        arm_frame = tk.LabelFrame(control_frame, text="ARM", padx=5, pady=5)
        arm_frame.pack(fill="x", pady=5)
        
        tk.Button(arm_frame, text="ACK pick-up", command=lambda: self.send_data("ARM_ACK_PICK", b'\x24\x24\x06\x04\xFF\xFF\x50\x23\x23')).pack(side=tk.LEFT, padx=5)
        tk.Button(arm_frame, text="ACK state (moving)", command=lambda: self.send_data("ARM_STATE_MOVING", b'\x24\x24\x06\x03\x01\x52\x23\x23')).pack(side=tk.LEFT, padx=5)
        tk.Button(arm_frame, text="ACK state (idle)", command=lambda: self.send_data("ARM_STATE_IDLE", b'\x24\x24\x06\x03\x00\x51\x23\x23')).pack(side=tk.LEFT, padx=5)
        
        # ACTOR buttons
        actor_frame = tk.LabelFrame(control_frame, text="ACTOR", padx=5, pady=5)
        actor_frame.pack(fill="x", pady=5)
        
        actor_cmd_row = tk.Frame(actor_frame)
        actor_cmd_row.pack(fill="x", pady=5)
        tk.Button(actor_cmd_row, text="ACK move forward", command=lambda: self.send_data("ACTOR_ACK_MOVE_FORWARD", b'\x24\x24\x05\x04\xFF\x50\x23\x23')).pack(side=tk.LEFT, padx=5)
        tk.Button(actor_cmd_row, text="ACK move backward", command=lambda: self.send_data("ACTOR_ACK_MOVE_BACKWARD", b'\x24\x24\x05\x04\xFF\x50\x23\x23')).pack(side=tk.LEFT, padx=5)
        tk.Button(actor_cmd_row, text="ACK stop", command=lambda: self.send_data("ACTOR_ACK_STOP", b'\x24\x24\x05\x04\xFF\x50\x23\x23')).pack(side=tk.LEFT, padx=5)
        tk.Button(actor_cmd_row, text="ACK turn 90", command=lambda: self.send_data("ACTOR_ACK_TURN", b'\x24\x24\x05\x04\xFF\x50\x23\x23')).pack(side=tk.LEFT, padx=5)
        
        actor_state_row = tk.Frame(actor_frame)
        actor_state_row.pack(fill="x", pady=5)
        tk.Button(actor_state_row, text="ACK state (no obstacle)", command=lambda: self.send_data("ACTOR_STATE_CLEAR", b'\x24\x24\x05\x03\x01\x64\xB5\x23\x23')).pack(side=tk.LEFT, padx=5)
        tk.Button(actor_state_row, text="ACK state (get obstacle)", command=lambda: self.send_data("ACTOR_STATE_OBSTACLE", b'\x24\x24\x05\x03\x01\x10\x61\x23\x23')).pack(side=tk.LEFT, padx=5)
        
        # Custom send frame
        custom_frame = tk.LabelFrame(self.root, text="Custom Command", padx=5, pady=5)
        custom_frame.pack(pady=5, padx=10, fill="x")
        
        tk.Label(custom_frame, text="Hex Data:").pack(side=tk.LEFT)
        self.custom_entry = tk.Entry(custom_frame, width=40)
        self.custom_entry.pack(side=tk.LEFT, padx=5)
        self.custom_entry.insert(0, "24 24 05 04 01 52 23 23")
        tk.Button(custom_frame, text="Send Hex", command=self.send_custom_hex).pack(side=tk.LEFT, padx=5)
        
        # Log area
        log_frame = tk.LabelFrame(self.root, text="Activity Log (Send & Receive)", padx=5, pady=5)
        log_frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, width=80)
        self.log_text.pack(fill="both", expand=True)
        
        # Log control buttons
        log_btn_frame = tk.Frame(log_frame)
        log_btn_frame.pack(pady=5)
        tk.Button(log_btn_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        tk.Button(log_btn_frame, text="Save Log", command=self.save_log).pack(side=tk.LEFT, padx=5)
        
    def log(self, message, color="black"):
        """Add message to log with timestamp and color."""
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, self.log, message, color)
            return

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_msg = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_msg)
        
        # Color coding for different message types
        if "📤 TX" in message:
            self.log_text.tag_add("tx", f"end-2l", f"end-1l")
            self.log_text.tag_config("tx", foreground="blue")
        elif "📥 RX" in message:
            self.log_text.tag_add("rx", f"end-2l", f"end-1l")
            self.log_text.tag_config("rx", foreground="green")
        elif "❌" in message:
            self.log_text.tag_add("error", f"end-2l", f"end-1l")
            self.log_text.tag_config("error", foreground="red")
        elif "✅" in message:
            self.log_text.tag_add("success", f"end-2l", f"end-1l")
            self.log_text.tag_config("success", foreground="darkgreen")
        
        self.log_text.see(tk.END)
        print(log_msg.strip())  # Also print to console
        
    def clear_log(self):
        """Clear the log area."""
        self.log_text.delete(1.0, tk.END)
        
    def save_log(self):
        """Save log to file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"serial_log_{timestamp}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.log_text.get(1.0, tk.END))
            self.log(f"💾 Log saved to {filename}")
        except Exception as e:
            self.log(f"❌ Save failed: {e}")
        
    def connect_serial(self):
        """Connect to COM15 and start receiving."""
        try:
            if self.serial_port and self.serial_port.is_open:
                self.disconnect_serial()
                
            self.serial_port = serial.Serial(
                port='COM21',
                baudrate=115200,
                timeout=1.0
            )
            
            self.status_label.config(text="Connected to COM15", fg="green")
            self.log("✅ Connected to COM15 successfully")
            
            # Start receiving thread
            self.start_receiving()
            
        except Exception as e:
            self.status_label.config(text=f"Connection Failed: {e}", fg="red")
            self.log(f"❌ Connection failed: {e}")
            
    def disconnect_serial(self):
        """Disconnect from COM15 and stop receiving."""
        try:
            # Stop receiving
            self.stop_receiving()
            
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self.serial_port = None
                
            self.status_label.config(text="Disconnected", fg="red")
            self.log("🔌 Disconnected from COM15")
            
        except Exception as e:
            self.log(f"❌ Disconnect error: {e}")
    
    def start_receiving(self):
        """Start receiving data in background thread."""
        if not self.receiving:
            self.receiving = True
            self.receive_thread = threading.Thread(target=self.receive_loop, daemon=True)
            self.receive_thread.start()
            self.receive_label.config(text="Receiving Data", fg="green")
            self.log("👁️ Started receiving data from COM15")
    
    def stop_receiving(self):
        """Stop receiving data."""
        self.receiving = False
        self.receive_label.config(text="Not Receiving", fg="orange")
        if self.receive_thread:
            self.receive_thread.join(timeout=1)
    
    def receive_loop(self):
        """Background thread to receive data from COM15."""
        while self.receiving and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    self.process_received_data(data)
                time.sleep(0.01)  # Small delay to prevent high CPU usage
                
            except Exception as e:
                self.log(f"❌ Receive error: {e}")
                break

    def send_loop(self):
        """Background thread to transmit queued frames without blocking the UI."""
        while True:
            item = self.send_queue.get()
            if item is None:
                break
            event_name, data = item
            if not self.serial_port or not self.serial_port.is_open:
                self.log(f"❌ Send aborted [{event_name}]: COM15 not connected")
                continue
            try:
                bytes_written = self.serial_port.write(data)
                hex_data = ' '.join(f'{b:02X}' for b in data)
                self.log(f"📤 TX [{event_name}]: {hex_data} ({bytes_written} bytes)")
            except serial.SerialException as e:
                self.log(f"❌ Send error [{event_name}]: {e}")
            except Exception as e:
                self.log(f"❌ Unexpected send error [{event_name}]: {e}")

    def process_received_data(self, data):
        """Process and display received data."""
        hex_data = ' '.join(f'{b:02X}' for b in data)
        self.log(f"📥 RX: {hex_data} ({len(data)} bytes)")
        
        # Try to parse as protocol frame
        if len(data) >= 7 and data[0:2] == b'\x24\x24':
            self.parse_protocol_frame(data)
        
        # Try to decode as ASCII text
        try:
            text = data.decode('utf-8', errors='ignore').strip()
            if text and all(c.isprintable() or c.isspace() for c in text):
                self.log(f"📝 ASCII: '{text}'")
        except:
            pass
    
    def parse_protocol_frame(self, data):
        """Parse protocol frame and show details."""
        try:
            if len(data) < 7:
                return
                
            header = data[0:2]
            length = data[2]
            group = data[3]
            payload = data[4:-3] if len(data) > 7 else b''
            crc = data[-3]
            footer = data[-2:]
            
            frame_info = f"📋 Frame: Header={header.hex()}, Len={length}, Group=0x{group:02X}, Payload={payload.hex()}, CRC=0x{crc:02X}, Footer={footer.hex()}"
            self.log(frame_info)
            
            # Interpret command
            if group == 0x04:  # Command
                if len(payload) > 0:
                    cmd = payload[0]
                    cmd_names = {
                        0x01: "MOVE_FORWARD",
                        0x02: "MOVE_BACKWARD", 
                        0x03: "STOP",
                        0x04: "TURN_90",
                        0x05: "READ_STATUS",
                        0xFF: "ACK"
                    }
                    cmd_name = cmd_names.get(cmd, f"UNKNOWN_0x{cmd:02X}")
                    self.log(f"🎯 Command: {cmd_name}")
            elif group == 0x03:  # Status
                self.log(f"📊 Status data received")
                
        except Exception as e:
            self.log(f"❌ Frame parse error: {e}")
            
    def send_data(self, event_name, data):
        """Send data directly to COM15."""
        if not self.serial_port or not self.serial_port.is_open:
            self.log("❌ Not connected to COM15!")
            return
        
        # Push send request to background thread to avoid blocking the UI
        self.send_queue.put((event_name, bytes(data)))
    
    def send_custom_hex(self):
        """Send custom hex data."""
        try:
            hex_str = self.custom_entry.get().strip()
            # Remove spaces and convert to bytes
            hex_str = hex_str.replace(" ", "").replace("0x", "")
            data = bytes.fromhex(hex_str)
            self.send_data("CUSTOM", data)
        except Exception as e:
            self.log(f"❌ Custom hex error: {e}")
            
    def run(self):
        """Start the simulator."""
        self.log("🚀 Simple Serial Simulator started (Send & Receive)")
        self.log("📋 Instructions:")
        self.log("   1. Click 'Connect COM15' to start")
        self.log("   2. Press buttons to SEND data")
        self.log("   3. Incoming data will be shown as RX")
        self.log("   4. Protocol frames are parsed automatically")
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()
        
    def on_closing(self):
        """Handle window closing."""
        self.disconnect_serial()
        # Stop send loop thread gracefully
        self.send_queue.put(None)
        if self._send_thread.is_alive():
            self._send_thread.join(timeout=1)
        self.root.destroy()

if __name__ == "__main__":
    print("=== Simple Serial Simulator (Send & Receive) ===")
    print("Features:")
    print("- Send data via button clicks")
    print("- Receive and display incoming data")
    print("- Parse protocol frames")
    print("- Color-coded logs")
    
    try:
        simulator = SimpleSerialSimulator()
        simulator.run()
    except KeyboardInterrupt:
        print("\n🛑 Simulator stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        input("Press Enter to exit...")

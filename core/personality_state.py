import datetime
import sqlite3
import os
from typing import Dict

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "memory", "aura_memory.db")

class PersonalityState:
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._ensure_table()

    def _ensure_table(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS personality_state (
                session_id TEXT PRIMARY KEY,
                energy_level INTEGER DEFAULT 5,
                frustration INTEGER DEFAULT 0,
                humor_frequency INTEGER DEFAULT 7,
                formality INTEGER DEFAULT 5,
                last_updated TEXT
            )
        ''')

        cursor.execute('SELECT * FROM personality_state WHERE session_id=?', (self.session_id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO personality_state
                (session_id, energy_level, frustration, humor_frequency, formality, last_updated)
                VALUES (?, 5, 0, 7, 5, ?)
            ''', (self.session_id, datetime.datetime.now().isoformat()))

        conn.commit()
        conn.close()

    def get_state(self) -> Dict:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM personality_state WHERE session_id=?', (self.session_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'session_id': row[0],
                'energy_level': row[1],
                'frustration': row[2],
                'humor_frequency': row[3],
                'formality': row[4],
                'last_updated': row[5]
            }
        return {}

    def update_state(self, energy_delta: int = 0, frustration_delta: int = 0,
                     humor_delta: int = 0, formality_delta: int = 0):
        state = self.get_state()

        new_energy = max(1, min(10, state['energy_level'] + energy_delta))
        new_frustration = max(0, min(10, state['frustration'] + frustration_delta))
        new_humor = max(1, min(10, state['humor_frequency'] + humor_delta))
        new_formality = max(1, min(10, state['formality'] + formality_delta))

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE personality_state
            SET energy_level=?, frustration=?, humor_frequency=?, formality=?, last_updated=?
            WHERE session_id=?
        ''', (new_energy, new_frustration, new_humor, new_formality,
              datetime.datetime.now().isoformat(), self.session_id))
        conn.commit()
        conn.close()

    def adjust_energy(self, task_type: str = "neutral"):
        if task_type == "success":
            self.update_state(energy_delta=1)
        elif task_type == "error":
            self.update_state(energy_delta=-1)
        elif task_type == "long_session":
            self.update_state(energy_delta=-2)

    def detect_frustration(self, error_count: int = 0, repeated_questions: int = 0):
        frustration_increase = error_count + (repeated_questions // 2)
        self.update_state(frustration_delta=frustration_increase)

    def reset_frustration(self):
        self.update_state(frustration_delta=-3)

    def get_tone_modifiers(self) -> Dict[str, str]:
        state = self.get_state()
        modifiers = []

        if state['energy_level'] < 3:
            modifiers.append("tired")
        if state['frustration'] > 7:
            modifiers.append("sympathetic")
        if state['humor_frequency'] > 8:
            modifiers.append("teasing")

        return {
            'tones': modifiers,
            'energy_level': state['energy_level'],
            'frustration': state['frustration'],
            'humor_frequency': state['humor_frequency']
        }

_state_instance = PersonalityState()

def get_state() -> Dict:
    return _state_instance.get_state()

def update_state(energy_delta: int = 0, frustration_delta: int = 0,
                 humor_delta: int = 0, formality_delta: int = 0):
    _state_instance.update_state(energy_delta, frustration_delta, humor_delta, formality_delta)

def adjust_energy(task_type: str = "neutral"):
    _state_instance.adjust_energy(task_type)

def detect_frustration(error_count: int = 0, repeated_questions: int = 0):
    _state_instance.detect_frustration(error_count, repeated_questions)

def reset_frustration():
    _state_instance.reset_frustration()

def get_tone_modifiers() -> Dict:
    return _state_instance.get_tone_modifiers()

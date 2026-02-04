import sqlite3
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path="data/parking.db"):
        self.db_path = db_path
        self.connection = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
    
    def create_tables(self):
        cursor = self.connection.cursor()
        
        # Пользователи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT NOT NULL,
                phone TEXT,
                car_plate TEXT,
                is_admin BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Парковочные места
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                spot_number TEXT NOT NULL,
                address TEXT NOT NULL,
                price_per_hour INTEGER NOT NULL,
                is_available BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            )
        ''')
        
        # Бронирования
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                spot_id INTEGER NOT NULL,
                hours INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (spot_id) REFERENCES spots(id)
            )
        ''')
        
        # Создаем админа
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (7884533080,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO users (telegram_id, full_name, is_admin)
                VALUES (?, ?, ?)
            ''', (7884533080, "Администратор", 1))
        
        self.connection.commit()
    
    # ========== ПОЛЬЗОВАТЕЛИ ==========
    def register_user(self, telegram_id, full_name, username=None):
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (telegram_id, username, full_name)
            VALUES (?, ?, ?)
        ''', (telegram_id, username, full_name))
        self.connection.commit()
        return cursor.lastrowid
    
    def get_user(self, telegram_id):
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return cursor.fetchone()
    
    def is_admin(self, telegram_id):
        user = self.get_user(telegram_id)
        return user and user['is_admin']
    
    # ========== МЕСТА ==========
    def add_spot(self, owner_id, spot_number, address, price_per_hour):
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT INTO spots (owner_id, spot_number, address, price_per_hour)
            VALUES (?, ?, ?, ?)
        ''', (owner_id, spot_number, address, price_per_hour))
        self.connection.commit()
        return cursor.lastrowid
    
    def get_spots(self, available_only=True):
        cursor = self.connection.cursor()
        if available_only:
            cursor.execute('''
                SELECT s.*, u.full_name as owner_name 
                FROM spots s 
                JOIN users u ON s.owner_id = u.id 
                WHERE s.is_available = 1
                ORDER BY s.created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT s.*, u.full_name as owner_name 
                FROM spots s 
                JOIN users u ON s.owner_id = u.id 
                ORDER BY s.created_at DESC
            ''')
        return cursor.fetchall()
    
    def get_spot(self, spot_id):
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT s.*, u.full_name as owner_name, u.telegram_id as owner_telegram
            FROM spots s 
            JOIN users u ON s.owner_id = u.id 
            WHERE s.id = ?
        ''', (spot_id,))
        return cursor.fetchone()
    
    def get_user_spots(self, owner_id):
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM spots 
            WHERE owner_id = ? 
            ORDER BY created_at DESC
        ''', (owner_id,))
        return cursor.fetchall()
    
    # ========== БРОНИРОВАНИЯ ==========
    def create_booking(self, user_id, spot_id, hours):
        spot = self.get_spot(spot_id)
        if not spot:
            return None
        
        total_price = spot['price_per_hour'] * hours
        
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT INTO bookings (user_id, spot_id, hours, total_price)
            VALUES (?, ?, ?, ?)
        ''', (user_id, spot_id, hours, total_price))
        
        # Помечаем место как занятое
        cursor.execute('''
            UPDATE spots SET is_available = 0 WHERE id = ?
        ''', (spot_id,))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def get_user_bookings(self, user_id):
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT b.*, s.spot_number, s.address, s.price_per_hour,
                   u.full_name as spot_owner
            FROM bookings b
            JOIN spots s ON b.spot_id = s.id
            JOIN users u ON s.owner_id = u.id
            WHERE b.user_id = ?
            ORDER BY b.created_at DESC
        ''', (user_id,))
        return cursor.fetchall()
    
    def get_all_bookings(self):
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT b.*, 
                   u1.full_name as client_name,
                   s.spot_number, s.address,
                   u2.full_name as owner_name
            FROM bookings b
            JOIN users u1 ON b.user_id = u1.id
            JOIN spots s ON b.spot_id = s.id
            JOIN users u2 ON s.owner_id = u2.id
            ORDER BY b.created_at DESC
        ''')
        return cursor.fetchall()
    
    # ========== АДМИН СТАТИСТИКА ==========
    def get_all_users(self):
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM users ORDER BY created_at DESC
        ''')
        return cursor.fetchall()
    
    def get_all_spots_admin(self):
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT s.*, u.full_name as owner_name, 
                   COUNT(b.id) as bookings_count,
                   SUM(b.total_price) as total_earnings
            FROM spots s
            LEFT JOIN users u ON s.owner_id = u.id
            LEFT JOIN bookings b ON s.id = b.spot_id
            GROUP BY s.id
            ORDER BY s.created_at DESC
        ''')
        return cursor.fetchall()

db = Database()
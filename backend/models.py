from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Initialize SQLAlchemy (to be bound to app in candlestickData)
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'created_at': self.created_at.isoformat()
        }


class TradeRecord(db.Model):
    __tablename__ = 'trade_records'

    id             = db.Column(db.Integer,   primary_key=True)
    user_id        = db.Column(db.Integer,   db.ForeignKey('users.id'), nullable=False)
    ticket         = db.Column(db.Integer,   nullable=False)           # MT5 trade ticket
    symbol         = db.Column(db.String(10), nullable=False)           # e.g. 'ETHUSD'
    type           = db.Column(db.String(4),  nullable=False)           # 'BUY' or 'SELL'
    volume         = db.Column(db.Float,     nullable=False)           # lot size
    entry_price    = db.Column(db.Float,     nullable=False)
    sl             = db.Column(db.Float)                                # stop‐loss price
    tp             = db.Column(db.Float)                                # take‐profit price
    entry_time     = db.Column(db.DateTime,  default=datetime.utcnow)   # open time
    exit_price     = db.Column(db.Float)                                # close price
    exit_time      = db.Column(db.DateTime)                             # close time
    profit_loss    = db.Column(db.Float)                                # P/L in account currency
    change_percent = db.Column(db.Float)                                # % change
    bot_id         = db.Column(db.String(50))                           # e.g. 'bot_1' or 'manual'
    bot_name       = db.Column(db.String(50))                           # e.g. 'BOT 1' or 'Manual'

    def to_dict(self):
        return {
            'id':             self.id,
            'ticket':         self.ticket,
            'symbol':         self.symbol,
            'type':           self.type,
            'volume':         self.volume,
            'entry_price':    self.entry_price,
            'sl':             self.sl,
            'tp':             self.tp,
            'entry_time':     self.entry_time.isoformat() if self.entry_time else None,
            'exit_price':     self.exit_price,
            'exit_time':      self.exit_time.isoformat() if self.exit_time else None,
            'profit_loss':    self.profit_loss,
            'change_percent': self.change_percent,
            'bot_id':         self.bot_id,
            'bot_name':       self.bot_name
        }
    


class TradeConfiguration(db.Model):
    __tablename__ = 'trade_configurations'

    id                    = db.Column(db.Integer, primary_key=True)
    ticket                = db.Column(db.BigInteger, unique=True, index=True, nullable=False)
    user_id               = db.Column(db.Integer)
    bot_id                = db.Column(db.String(50))
    bot_name              = db.Column(db.String(50))
    strategy              = db.Column(db.String(50))
    magic_number          = db.Column(db.Integer)
    entry_time            = db.Column(db.DateTime)

    profit_loss           = db.Column(db.Float)
    change_percent        = db.Column(db.Float)

    max_risk_per_trade    = db.Column(db.Float)
    trade_size_usd        = db.Column(db.Float)
    leverage              = db.Column(db.String(10))
    asset_type            = db.Column(db.String(20))

    risk_reward_ratio     = db.Column(db.Float)
    stop_loss_pips        = db.Column(db.Float)
    take_profit_pips      = db.Column(db.Float)
    max_loss_threshold    = db.Column(db.Float)

    entry_trigger         = db.Column(db.String(50))
    exit_trigger          = db.Column(db.String(50))
    max_daily_trades      = db.Column(db.Integer)
    time_window           = db.Column(db.String(20))

    rsi_period            = db.Column(db.Integer)
    moving_average_period = db.Column(db.Integer)
    bollinger_bands_period= db.Column(db.Integer)
    bb_deviation          = db.Column(db.Float)

    auto_stop_enabled     = db.Column(db.Boolean)
    max_consecutive_losses= db.Column(db.Integer)
    auto_trading_enabled  = db.Column(db.Boolean)

    created_at            = db.Column(db.DateTime, default=datetime.utcnow)


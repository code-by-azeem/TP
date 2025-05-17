import React from 'react';
import './Modal.css';

const Modal = ({ isOpen, onClose, title, message, type = 'info', autoCloseDelay = 0, actionButton = null }) => {
  React.useEffect(() => {
    if (isOpen && autoCloseDelay > 0) {
      const timer = setTimeout(() => {
        onClose();
      }, autoCloseDelay);
      return () => clearTimeout(timer);
    }
  }, [isOpen, autoCloseDelay, onClose]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-container">
        <div className={`modal-header ${type}`}>
          <h3>{title}</h3>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <p>{message}</p>
        </div>
        <div className="modal-footer">
          {actionButton ? (
            <button className="modal-action-button" onClick={actionButton.onClick}>
              {actionButton.text}
            </button>
          ) : (
            <button className="modal-button" onClick={onClose}>OK</button>
          )}
        </div>
      </div>
    </div>
  );
};

export default Modal; 
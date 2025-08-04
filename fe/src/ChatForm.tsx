import React, { useState, useEffect, useRef } from 'react';

const ChatForm = () => {
  const [messages, setMessages] = useState<any>([]);
  const [newMessage, setNewMessage] = useState('');
  const messagesEndRef = useRef<any>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleInputChange = (e) => {
    setNewMessage(e.target.value);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (newMessage.trim()) {

      setMessages([...messages, { id: Date.now(), text: newMessage, sender: 'You' }]);
      setNewMessage('');
    }
  };

  return (
    <div className="chat-container">
      <div className="messages-display">
        {messages.length === 0 ? (
          <p className="no-messages">Bắt đầu cuộc trò chuyện!</p>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`message-bubble ${msg.sender === 'You' ? 'sent' : 'received'}`}>
              <span className="sender-name">{msg.sender}:</span> {msg.text}
            </div>
          ))
        )}
        <div ref={messagesEndRef} /> {/* Element dùng để cuộn xuống cuối */}
      </div>
      <form onSubmit={handleSubmit} className="message-input-form">
        <input
          type="text"
          value={newMessage}
          onChange={handleInputChange}
          placeholder="Nhập tin nhắn của bạn..."
          className="message-input"
        />
        <button type="submit" className="send-button">Gửi</button>
      </form>
    </div>
  );
};

export default ChatForm;
import React, { useState, useEffect, useRef } from 'react';
import { config } from './core/config';

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (newMessage.trim()) {

      setMessages([...messages, { id: Date.now(), text: newMessage, sender: 'You' }]);
      setNewMessage('');
      
      const data = new FormData();
      data.append("query_text", newMessage)
      data.append("uid", localStorage.getItem("uid"))

      try{
        const response = await fetch(`${config.apiUrl}/v1/retrieve`, {
          method: 'post',
          body: data
        });

        const result = await response.json();

        if (response.ok){
          setMessages(prevState => {
            return prevState.concat({
              id: Date.now(),
              text: result['message'],
              sender: 'ChatBot'
            })
          });
          setNewMessage('');
        }else{
          setMessages(prevState => {
            return prevState.concat({
              id: Date.now(),
              text: 'Đã có lỗi bất ngờ! Bạn hãy thử lại sau nhé.',
              sender: 'ChatBot'
            })
          });
          setNewMessage('');
        }
      }catch(error){
        console.error(error);
      }
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
import ChatForm from "./ChatForm";
import FileUpload from "./FileUpload";

export default function ChatComponent() {
  return (
    <div className="chat-component">
      <div className="chat-header">
        <FileUpload />
      </div>
      <div className="chat-body">
        <ChatForm/>
      </div>
    </div>
  );
}
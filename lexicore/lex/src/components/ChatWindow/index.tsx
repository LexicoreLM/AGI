import './ChatWindow.css';
import {MessageData} from "../../interface/MessageData";
import MessagesList from "./MessagesList";
import ChatInput from "./ChatInput";

const messages: MessageData[] = [{
    id: '123',
    query: 'Hello, I need your help',
    response: 'Sure! How can I help you?'
},
]

const ChatWindow = () => {

    return <section className="chat__container">
        <MessagesList  messages={messages} />
        <ChatInput />
    </section>
}

export default ChatWindow;
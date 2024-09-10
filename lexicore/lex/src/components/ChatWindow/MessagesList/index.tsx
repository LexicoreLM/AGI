import './MessagesList.css';
import {MessageData} from "../../../interface/MessageData";
import Message from "./Message";

interface MessagesListProps {
    messages: MessageData[];
}

const MessagesList = ({messages}: MessagesListProps) => {
    return <div className="messages-list">
        {messages.map((m) => <>
                <Message key={m.id} text={m.query} isUser />
                <Message key={m.id} text={m.response}/>
            </>
        )}
    </div>
}

export default MessagesList;
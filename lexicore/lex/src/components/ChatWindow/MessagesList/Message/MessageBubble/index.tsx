import './MessageBubble.css';
import classNames from "classnames";

interface MessageBubbleProps {
    isUser: boolean;
    text: string;
}
const MessageBubble = ({isUser, text}: MessageBubbleProps) => {
    return <div className={classNames({
        "message-bubble": true,
        user: isUser,
    })}>
        {text}
    </div>
}

export default MessageBubble;
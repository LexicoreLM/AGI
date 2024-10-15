import MessageWrapper from "./MessageWrapper";
import {PropsWithChildren} from "react";
import MessageBubble from "./MessageBubble";

interface MessageWrapperProps extends PropsWithChildren {
    text: string;
    isUser?: boolean;
}

const Message = ({text, isUser}: MessageWrapperProps) => {
    return <MessageWrapper isUser={!!isUser}>
        <MessageBubble isUser={!!isUser} text={text} />
    </MessageWrapper>
}

export default Message;
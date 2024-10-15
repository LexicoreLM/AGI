import classNames from "classnames";
import './MessageWrapper.css';
import {PropsWithChildren} from "react";
import Logo from "../../../../Logo";
interface MessageWrapperProps extends PropsWithChildren {
    isUser: boolean;
}
const MessageWrapper = ({isUser, children}: MessageWrapperProps) => {
    return <div className={classNames({
        "message__wrapper": true,
        user: isUser,
    })}>
        {!isUser && <div className="message__avatar"><Logo /></div>}
        {children}
    </div>
}

export default MessageWrapper;
import {FormControl, IconButton, Input, InputAdornment, InputLabel, OutlinedInput} from '@mui/material';
import './ChatInput.css';
import React, {useCallback, useState} from "react";
import SendIcon from '@mui/icons-material/Send';
const ChatInput = () => {
    const [text, setText] = useState<string>("");

    const handleSend = useCallback(() => null, []);

    const handleChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
        setText(event.target.value);
    }, [setText]);

    return <div className="chat-input">
        <OutlinedInput
            fullWidth
            multiline
            maxRows={4}
            value={text}
            onChange={handleChange}
            placeholder="Input your text here..."
            endAdornment={
                <InputAdornment position="end">
                    <IconButton onClick={handleSend} disabled={!text.trim()} color="primary">
                        <SendIcon />
                    </IconButton>
                </InputAdornment>
            }
        />
    </div>
}

export default ChatInput;
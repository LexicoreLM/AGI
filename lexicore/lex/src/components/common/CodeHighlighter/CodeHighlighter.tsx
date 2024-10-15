import Prism from 'prismjs';
import {PropsWithChildren, useEffect, useMemo} from 'react';
import 'prismjs/themes/prism-tomorrow.css';
import 'prismjs/components/prism-json';
import './CodeHighlighter.css';
import {IconButton} from "@mui/material";
import ContentCopyIcon from '@mui/icons-material/ContentCopy';

interface CodeHighlighterProps extends PropsWithChildren {
    lang?: string | undefined;
    inline?: boolean | undefined;
}

const CodeHighlighter = ({lang, children}: CodeHighlighterProps) => {
    useEffect(() => {
        Prism.highlightAll();
    }, [children]);

    const className = useMemo(() => {
        if (!lang) return 'lang-markup';
        if (lang.startsWith('lang-')) return lang;
        return `lang-${lang}`;
    }, [lang]);

    return (
        <section className="code__container">
            <div className="code__controls">
                <IconButton>
                    <ContentCopyIcon/>
                </IconButton>
            </div>
            <code className={className}>{children}</code>
        </section>
    );
};

export default CodeHighlighter;

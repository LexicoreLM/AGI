import './RenderedDataView.css';
import remarkGfm from "remark-gfm";
import ReactMarkdown from "react-markdown";
import {Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow} from "@mui/material";

interface RenderedDataViewProps {
    data: string;
}

interface NodeChildType {
    value: string;
}
const RenderedDataView = ({ data }: RenderedDataViewProps) => {
    return <div className="data-preview__container">
        <ReactMarkdown remarkPlugins={[remarkGfm]}
                       components={{
                           th: ({node}) => {
                               return <TableCell>{(node?.children?.[0] as NodeChildType)?.value}</TableCell>
                           },
                           td: ({node}) => <TableCell>{(node?.children?.[0] as NodeChildType)?.value}</TableCell>,
                           tr: ({children}) => {
                               return <TableRow>{children}</TableRow>
                           },
                           table: ({children}) => {
                               return <TableContainer component={Paper}>
                                   <Table>{children}</Table>
                               </TableContainer>
                           },
                           thead: ({children}) => {
                               return <TableHead sx={{
                                   background: 'rgba(255, 255, 255, 0.2)'
                               }}>{children}</TableHead>
                           },
                           tbody: ({children}) => {
                               return <TableBody sx={{
                                   background: 'rgba(255, 255, 255, 0.1)'
                               }}>
                                   {children}
                               </TableBody>
                           },
                       }}
        >
            {data}
        </ReactMarkdown>
    </div>
}

export default RenderedDataView;
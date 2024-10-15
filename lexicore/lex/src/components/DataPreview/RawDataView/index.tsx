import './RawDataView.css';
import CodeHighlighter from "../../common/CodeHighlighter/CodeHighlighter";
import mockedData from "../../../configs/mockedData.json";
interface RawDataViewProps {
    data: string;
}

const RawDataView = ({data}: RawDataViewProps) => {
    return <div className="data-preview__container">
        <CodeHighlighter lang="lang-json">
            {JSON.stringify(mockedData, null, 4)}
        </CodeHighlighter>
    </div>
}

export default RawDataView;
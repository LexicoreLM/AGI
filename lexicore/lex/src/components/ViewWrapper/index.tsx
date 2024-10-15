import {PropsWithChildren} from "react";
import Navbar from "../Navbar";
import './ViewWrapper.css';

const ViewWrapper = ({children}: PropsWithChildren) => {
    return (
        <div className="view__wrapper">
            <Navbar/>
            <section className="view__content-container">
                <div className="view__content">
                    {children}
                </div>
            </section>
        </div>
    )
}

export default ViewWrapper;
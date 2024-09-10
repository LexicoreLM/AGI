import './Navbar.css';
import Logo from "../Logo";

const Navbar = () => {
    return <nav id="navbar">
        <div className="navbar__logo">
            <Logo/>
        </div>
    </nav>
}

export default Navbar;
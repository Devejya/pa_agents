import { Link } from 'react-router-dom'
import styles from './Header.module.css'

export function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.container}>
        <Link to="/" className={styles.logo}>
          <span className={styles.logoMark}>Y</span>
          <span className={styles.logoText}>Yennifer</span>
        </Link>
      </div>
    </header>
  )
}


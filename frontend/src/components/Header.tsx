import styles from './Header.module.css'

export function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.container}>
        <div className={styles.logo}>
          <span className={styles.logoMark}>Y</span>
          <span className={styles.logoText}>Yennifer</span>
        </div>
      </div>
    </header>
  )
}


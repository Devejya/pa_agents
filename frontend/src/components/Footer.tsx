import styles from './Footer.module.css'

export function Footer() {
  const currentYear = new Date().getFullYear()
  
  return (
    <footer className={styles.footer}>
      <div className={styles.container}>
        <div className={styles.brand}>
          <span className={styles.logoMark}>Y</span>
          <span className={styles.logoText}>Yennifer</span>
        </div>
        <p className={styles.tagline}>
          Your AI executive assistant, available 24/7.
        </p>
        <p className={styles.copyright}>
          © {currentYear} Yennifer AI. All rights reserved.
        </p>
      </div>
    </footer>
  )
}


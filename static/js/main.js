// IAMSTECH Main JavaScript
document.addEventListener('DOMContentLoaded', () => {
    console.log('IAMSTECH Portal Initialized');
    
    // Add subtle reveal animations for floating cards
    const cards = document.querySelectorAll('.floating-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        setTimeout(() => {
            card.style.opacity = '1';
            card.style.transition = 'opacity 1s ease-out';
        }, 500 + (index * 200));
    });
});

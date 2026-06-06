document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('form');
    const pw = document.querySelector('[name="password"]');
    const cpw = document.querySelector('[name="confirm_password"]');

    if (cpw && pw) {
        cpw.addEventListener('input', function() {
            cpw.setCustomValidity('');
            if (pw.value && cpw.value && pw.value !== cpw.value) {
                cpw.setCustomValidity('Passwords do not match.');
            }
        });
    }

    form.addEventListener('submit', function(e) {
        if (cpw) {
            cpw.setCustomValidity('');
        }

        if (pw && cpw && pw.value.trim() === '' && cpw.value.trim() === '') {
            return;
        }

        if (pw && cpw && pw.value !== cpw.value) {
            e.preventDefault();
            cpw.setCustomValidity('Passwords do not match.');
            cpw.reportValidity();
        }
    });
});


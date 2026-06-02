fetch('https://api.deadlock-api.com/v1/players/105130498/rank-predict')
    .then(response => response.json())
    .then(data => displayRank(data))
    .catch(error => console.error('Error:', error));

function displayRank(data) {
    console.log(data);
    const rankContainer = document.getElementById('rank');
    rankContainer.innerHTML = 'test';
}
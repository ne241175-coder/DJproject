let x = 0;

function setup(){
    createCanvas(600, 400);
}

function draw(){
    background(220);
    ellipse(x, 200, 80, 80);
    square(250, x*(2/3), 60);
    x += 3;
    if(x == 600){
        x = 0;
    }
}